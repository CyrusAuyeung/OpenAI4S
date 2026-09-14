"""A host-built matplotlib font list for kernels in an enforced sandbox.

An enforced sandbox gives every kernel a private, empty ``MPLCONFIGDIR``
(``KernelSandbox.apply_environment``), so the first ``import matplotlib`` in
each new kernel rebuilds the font list from scratch. On macOS that shells out
to ``system_profiler SPFontsDataType``: 8-48 seconds before the first plot of
every new, restarted-into-a-new-sandbox, or new-generation Python kernel.

The obvious cures open a channel the sandbox exists to close. A cache
directory every kernel may write is one Cell poisoning the font list another
session's kernel parses; copying a kernel's rebuilt list back out after it
exits is the same channel with a delay. So the list a kernel is seeded with is
only ever produced by a *builder* the host runs for that purpose:

* The builder is the kernel's own interpreter, run through the same confined
  probe path as the package freeze (``preinstall.run_confined_probe``: the
  scrubbed child environment and the OS sandbox), on a fixed program that
  imports matplotlib's font manager into a fresh empty cache directory. It
  resolves matplotlib as that interpreter's kernels do (no ``-I``: a user-site
  install must be found, or the list would never be built for it) with one
  deliberate difference: the working-directory entry ``python -c`` puts first
  on ``sys.path`` is dropped before any other import, and the probe runs in
  its own empty directory anyway. Otherwise a ``json.py`` in the daemon's
  launch directory -- which a CLI kernel's workspace can be -- would decide
  what the builder prints. No Cell code runs, and what remains on its import
  path is what every kernel on that interpreter already imports from before
  its first Cell, so its output carries the trust of the environment itself.
* The host validates what it prints (name, size, JSON shape, version agreeing
  with the name) and writes it under ``<data_dir>/cache/matplotlib-fonts``,
  keyed by interpreter path. Kernels cannot write there: an enforced sandbox
  only grants its workspace and its own temp, and a cache that happens to lie
  inside a kernel's workspace is refused rather than trusted.
* Each new kernel receives a *copy* inside its private temp, placed through
  directory descriptors that refuse symlinks, before its worker starts.

The list is only reused while the font directories matplotlib scans look the
way they did when it was built, so installing a font (a CJK face for Chinese
labels, say) is picked up by the next kernel rather than hidden behind a stale
cache. It is also pinned to the ``font_manager.py`` it was built by (that
file's size and modification time, as the builder saw it and the host still
sees it): matplotlib names its list after its own version, so after an
upgrade in that environment an old list would be ignored inside every new
kernel, each scanning again, while the cache still looked valid. A changed
install is rebuilt instead. ``MAX_CACHE_AGE_S`` backstops sources neither
check can see.

Builds happen in the background and only in a process that called
:func:`enable_background_builds` -- the daemon does, from ``run_server``. A
one-shot CLI run or a test only ever *reads* an existing cache, so neither
starts a font scan it would abandon at exit. Everything here is best effort: a
missing, stale, or unreadable cache means the kernel builds its own list, as it
always did, and never that the kernel fails to start.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

_CACHE_PARTS = ("cache", "matplotlib-fonts")
_MANIFEST_NAME = "manifest.json"
_MANIFEST_FORMAT = 2
_MARKER = "__OPENAI4S_FONTLIST__"
_FONTLIST_NAME = re.compile(r"fontlist-v[0-9][0-9A-Za-z.+_-]{0,63}\.json")

#: A macOS font list is a few hundred kilobytes; this is a sanity ceiling on
#: what the host will read back from a builder or copy into a kernel.
MAX_FONTLIST_BYTES = 16 * 1024 * 1024
#: Rebuild (in the background, still seeding meanwhile) after this long, for
#: font sources the directory fingerprint cannot observe.
MAX_CACHE_AGE_S = 30 * 24 * 3600
#: A cold macOS font scan was measured at 8-48 seconds under load.
BUILD_TIMEOUT_S = 300.0
#: How long a failed build (no matplotlib in that interpreter, a timeout) is
#: remembered before a later kernel spawn may try again.
RETRY_FAILED_BUILD_AFTER_S = 600.0

_MAX_FINGERPRINT_DIRS = 4096
_MAX_FINGERPRINT_DEPTH = 4

# `python -c` puts the working directory ('') first on `sys.path`, ahead of
# the stdlib. The confined probe runs in its own empty directory, but the
# program does not rely on its runner for that: before any import that is not
# already loaded at startup (`sys` is built in), it drops that entry, so a
# `json.py` or a `matplotlib/` wherever the child was started cannot answer.
_BUILDER = (
    "import sys\n"
    "sys.path[:] = [entry for entry in sys.path if entry not in ('', '.')]\n"
    "import json, os, shutil, tempfile\n"
    "cache = tempfile.mkdtemp(prefix='openai4s-fontlist-')\n"
    "os.environ['MPLCONFIGDIR'] = cache\n"
    "try:\n"
    "    import matplotlib\n"
    "    from matplotlib import font_manager\n"
    "    name = 'fontlist-v%s.json' % (font_manager.FontManager.__version__,)\n"
    "    with open(os.path.join(matplotlib.get_cachedir(), name), encoding='utf-8') as handle:\n"
    "        content = handle.read()\n"
    "    source = os.path.abspath(font_manager.__file__)\n"
    "    info = os.stat(source)\n"
    "except Exception as error:\n"
    f"    print({_MARKER!r} + json.dumps({{'error': type(error).__name__}}))\n"
    "else:\n"
    f"    print({_MARKER!r} + json.dumps({{'name': name, 'content': content,"
    " 'source': source, 'source_stat': [info.st_mtime_ns, info.st_size]}))\n"
    "finally:\n"
    "    shutil.rmtree(cache, ignore_errors=True)\n"
)

Runner = Callable[..., Any]

_state_lock = threading.Lock()
_builds_data_dir: list[Path | None] = [None]
_inflight: set[Path] = set()
_failed_at: dict[Path, float] = {}


def _default_data_dir() -> Path:
    with _state_lock:
        configured = _builds_data_dir[0]
    if configured is not None:
        return configured
    env = os.environ.get("OPENAI4S_DATA_DIR")
    return Path(env).expanduser() if env else Path.home() / ".openai4s"


def cache_directory(
    interpreter: str, data_dir: str | os.PathLike[str] | None = None
) -> Path:
    """Where the host keeps the font list built for one interpreter path."""

    root = Path(data_dir) if data_dir is not None else _default_data_dir()
    identity = os.path.abspath(str(interpreter))
    key = hashlib.sha256(identity.encode("utf-8", "surrogateescape")).hexdigest()
    return root.joinpath(*_CACHE_PARTS, key[:32])


def _font_roots(platform_name: str, home: Path) -> list[Path]:
    # The directories matplotlib's own font search walks
    # (`OSXFontDirectories` / `X11FontDirectories`).
    if platform_name == "darwin":
        roots = [
            Path("/Library/Fonts"),
            Path("/Network/Library/Fonts"),
            Path("/System/Library/Fonts"),
            Path("/opt/local/share/fonts"),
            home / "Library" / "Fonts",
        ]
        # Fonts downloaded on demand (Font Book, a CJK face) land here, and
        # matplotlib's `system_profiler` scan lists them.
        try:
            roots.extend(
                sorted(
                    Path("/System/Library/AssetsV2").glob("com_apple_MobileAsset_Font*")
                )
            )
        except OSError:
            pass
        return roots
    # A kernel does not inherit XDG_DATA_HOME (kernel/environment.py), so its
    # matplotlib looks under the home default, and so does this fingerprint.
    return [
        Path("/usr/X11R6/lib/X11/fonts/TTF"),
        Path("/usr/X11/lib/X11/fonts"),
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/usr/lib/openoffice/share/fonts/truetype"),
        home / ".local" / "share" / "fonts",
        home / ".fonts",
    ]


def font_directory_fingerprint(
    roots: Sequence[str | os.PathLike[str]] | None = None,
) -> str:
    """A digest of the font directories' shapes and modification times.

    Adding or removing a font file changes its directory's mtime, so a font
    installed after the list was built changes the fingerprint and the next
    kernel builds a fresh list instead of being seeded with one that lacks it.
    Directories only, bounded in count and depth: this runs on every spawn.
    """

    if roots is None:
        roots = _font_roots(sys.platform, Path.home())
    digest = hashlib.sha256()
    budget = [_MAX_FINGERPRINT_DIRS]

    def visit(path: str, depth: int) -> None:
        if budget[0] <= 0:
            digest.update(b"<truncated>\n")
            return
        budget[0] -= 1
        try:
            info = os.stat(path)
        except OSError:
            digest.update(f"{path}\0-\n".encode("utf-8", "surrogateescape"))
            return
        digest.update(
            f"{path}\0{info.st_mtime_ns}\n".encode("utf-8", "surrogateescape")
        )
        if depth >= _MAX_FINGERPRINT_DEPTH:
            return
        try:
            with os.scandir(path) as entries:
                children = sorted(
                    entry.path
                    for entry in entries
                    if entry.is_dir(follow_symlinks=False)
                )
        except OSError:
            return
        for child in children:
            visit(child, depth + 1)

    for root in roots:
        visit(str(root), 0)
    return digest.hexdigest()


def enable_background_builds(data_dir: str | os.PathLike[str] | None = None) -> None:
    """Let kernel spawns in this process build a missing or stale font list."""

    root = Path(data_dir) if data_dir is not None else None
    with _state_lock:
        if root is None:
            env = os.environ.get("OPENAI4S_DATA_DIR")
            root = Path(env).expanduser() if env else Path.home() / ".openai4s"
        _builds_data_dir[0] = root


def disable_background_builds() -> None:
    with _state_lock:
        _builds_data_dir[0] = None


def request_build(
    interpreter: str,
    *,
    data_dir: str | os.PathLike[str] | None = None,
    runner: Runner | None = None,
) -> threading.Thread | None:
    """Start one background build for ``interpreter`` if builds are enabled.

    Single-flight per cache directory, and a failed build is not retried on
    every spawn. Returns the thread so a caller that must wait can join it.
    """

    with _state_lock:
        enabled = _builds_data_dir[0]
    if enabled is None:
        return None
    root = Path(data_dir) if data_dir is not None else enabled
    cache = cache_directory(interpreter, root)
    now = time.monotonic()
    with _state_lock:
        if cache in _inflight:
            return None
        failed = _failed_at.get(cache)
        if failed is not None and now - failed < RETRY_FAILED_BUILD_AFTER_S:
            return None
        _inflight.add(cache)

    def work() -> None:
        built = None
        try:
            built = build_font_cache(interpreter, data_dir=root, runner=runner)
        except Exception:  # noqa: BLE001 - a background cache never raises
            built = None
        finally:
            with _state_lock:
                _inflight.discard(cache)
                if built is None:
                    _failed_at[cache] = time.monotonic()
                else:
                    _failed_at.pop(cache, None)

    thread = threading.Thread(target=work, name="openai4s-font-cache", daemon=True)
    try:
        thread.start()
    except RuntimeError:
        with _state_lock:
            _inflight.discard(cache)
        return None
    return thread


def _validated_fontlist(name: Any, content: Any) -> bytes | None:
    if not isinstance(name, str) or not _FONTLIST_NAME.fullmatch(name):
        return None
    if not isinstance(content, str):
        return None
    data = content.encode("utf-8")
    if len(data) > MAX_FONTLIST_BYTES:
        return None
    try:
        parsed = json.loads(content)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or parsed.get("__class__") != "FontManager":
        return None
    version = parsed.get("_version")
    if not isinstance(version, str) or name != f"fontlist-v{version}.json":
        return None
    return data


def _install_identity(source: Any) -> list[int] | None:
    """The size and mtime of the ``font_manager.py`` a list was built by.

    Replacing matplotlib (``pip install -U``, a new conda build) rewrites that
    file, so this changes with the version that names the list. A stat, not a
    read or an import: it runs on every enforced kernel spawn.
    """

    if not isinstance(source, str) or not os.path.isabs(source):
        return None
    try:
        info = os.stat(source)
    except (OSError, ValueError):
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return [info.st_mtime_ns, info.st_size]


def _builder_payload(stdout: Any) -> dict | None:
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if not isinstance(stdout, str):
        return None
    for line in reversed(stdout.splitlines()):
        if line.startswith(_MARKER):
            try:
                payload = json.loads(line[len(_MARKER) :])
            except ValueError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def _write_atomically(directory: Path, name: str, data: bytes) -> None:
    temporary = directory / f".{name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, directory / name)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def build_font_cache(
    interpreter: str,
    *,
    data_dir: str | os.PathLike[str] | None = None,
    runner: Runner | None = None,
    timeout: float = BUILD_TIMEOUT_S,
) -> Path | None:
    """Build and store one interpreter's font list; the stored path or None."""

    cache = cache_directory(interpreter, data_dir)
    # Taken before the scan: a font installed while it runs then makes the
    # next spawn rebuild, instead of trusting a list that may predate it.
    fingerprint = font_directory_fingerprint()
    if runner is None:
        from openai4s.kernel.preinstall import run_confined_probe

        runner = run_confined_probe
    try:
        completed = runner([str(interpreter), "-c", _BUILDER], timeout=timeout)
    except Exception:  # noqa: BLE001 - enforce without a boundary, timeout, OSError
        return None
    if getattr(completed, "returncode", 1) != 0:
        return None
    payload = _builder_payload(getattr(completed, "stdout", None))
    if payload is None:
        return None
    name = payload.get("name")
    data = _validated_fontlist(name, payload.get("content"))
    if data is None:
        return None
    source = payload.get("source")
    identity = _install_identity(source)
    if identity is None or payload.get("source_stat") != identity:
        # Unpinnable, or matplotlib changed between the builder's import and
        # now: a list stored here could not tell a later upgrade apart.
        return None
    manifest = {
        "format": _MANIFEST_FORMAT,
        "interpreter": os.path.abspath(str(interpreter)),
        "fontlist": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "fingerprint": fingerprint,
        "matplotlib_source": source,
        "matplotlib_identity": identity,
        "built_at": time.time(),
    }
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_atomically(cache, str(name), data)
    # The manifest is written last: it is what makes the new list current.
    _write_atomically(
        cache, _MANIFEST_NAME, json.dumps(manifest, sort_keys=True).encode("utf-8")
    )
    return cache / str(name)


def _read_regular_file(path: Path, limit: int) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            return None
        data = handle.read(limit + 1)
    return data if len(data) <= limit else None


def _place_privately(temp_dir: str, subdir: str, name: str, data: bytes) -> bool:
    """Write ``temp_dir/subdir/name`` without following any symlink on the way."""

    # `os.replace` shares `os.rename`'s renameat(2) path; only the latter is
    # listed in `supports_dir_fd`.
    needed = (os.open, os.mkdir, os.rename)
    if not all(function in os.supports_dir_fd for function in needed):
        return False
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    parent = os.open(temp_dir, directory_flags)
    try:
        try:
            os.mkdir(subdir, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        child = os.open(subdir, directory_flags, dir_fd=parent)
        try:
            temporary = f".{name}.{uuid.uuid4().hex}.tmp"
            file_flags = (
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(temporary, file_flags, 0o600, dir_fd=child)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            os.replace(temporary, name, src_dir_fd=child, dst_dir_fd=child)
        finally:
            os.close(child)
    finally:
        os.close(parent)
    return True


def _inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        base = root.resolve(strict=False)
    except (OSError, RuntimeError):
        return True
    return resolved == base or base in resolved.parents


def seed_kernel_font_cache(
    sandbox: Any,
    *,
    interpreter: str,
    data_dir: str | os.PathLike[str] | None = None,
    runner: Runner | None = None,
) -> bool:
    """Copy the host-built font list into a new kernel's private MPLCONFIGDIR.

    Call before the worker starts. True when a list was placed; never raises.
    """

    try:
        return _seed(sandbox, interpreter=interpreter, data_dir=data_dir, runner=runner)
    except Exception:  # noqa: BLE001 - seeding is an optimisation, not a gate
        return False


def _seed(
    sandbox: Any,
    *,
    interpreter: str,
    data_dir: str | os.PathLike[str] | None,
    runner: Runner | None,
) -> bool:
    status = getattr(sandbox, "status", None)
    temp_dir = getattr(status, "temp_dir", None)
    if not getattr(status, "enforced", False) or not temp_dir:
        return False
    # Ask the sandbox where it points matplotlib rather than restating it, and
    # only ever write directly below that kernel's own private temp.
    target = sandbox.apply_environment({}).get("MPLCONFIGDIR")
    if not target or Path(target).parent != Path(temp_dir):
        return False
    cache = cache_directory(interpreter, data_dir)
    workspace = getattr(status, "workspace", None)
    if workspace and _inside(cache, Path(workspace)):
        # A kernel may write its own workspace, so a cache inside one is not
        # something the host built -- whatever it contains.
        return False

    def rebuild() -> None:
        request_build(interpreter, data_dir=data_dir, runner=runner)

    raw_manifest = _read_regular_file(cache / _MANIFEST_NAME, 64 * 1024)
    try:
        manifest = json.loads(raw_manifest) if raw_manifest is not None else None
    except ValueError:
        manifest = None
    installed = (
        _install_identity(manifest.get("matplotlib_source"))
        if isinstance(manifest, dict)
        else None
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != _MANIFEST_FORMAT
        or manifest.get("interpreter") != os.path.abspath(str(interpreter))
        or not isinstance(manifest.get("fontlist"), str)
        or not _FONTLIST_NAME.fullmatch(manifest["fontlist"])
        # matplotlib upgraded or removed since the build: its list is named
        # for another version now, so seeding this one would save nothing.
        or installed is None
        or installed != manifest.get("matplotlib_identity")
        or manifest.get("fingerprint") != font_directory_fingerprint()
    ):
        rebuild()
        return False
    name = manifest["fontlist"]
    data = _read_regular_file(cache / name, MAX_FONTLIST_BYTES)
    if data is None or hashlib.sha256(data).hexdigest() != manifest.get("sha256"):
        rebuild()
        return False
    built_at = manifest.get("built_at")
    if (
        not isinstance(built_at, (int, float))
        or time.time() - built_at > MAX_CACHE_AGE_S
    ):
        rebuild()
    return _place_privately(str(temp_dir), Path(target).name, name, data)


__all__ = [
    "BUILD_TIMEOUT_S",
    "MAX_CACHE_AGE_S",
    "MAX_FONTLIST_BYTES",
    "build_font_cache",
    "cache_directory",
    "disable_background_builds",
    "enable_background_builds",
    "font_directory_fingerprint",
    "request_build",
    "seed_kernel_font_cache",
]
