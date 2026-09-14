"""The matplotlib font list a sandboxed kernel starts with, and who built it.

An enforced sandbox gives every kernel an empty private MPLCONFIGDIR, so the
first plot in each new kernel rebuilt matplotlib's font list from scratch --
8-48 seconds on macOS, where the scan shells out to `system_profiler`. The cure
must not become a channel between kernels: the list a kernel is seeded with is
built by the host (the kernel's interpreter, confined, running a fixed program)
and copied *into* each new kernel's private temp, never read back out of one.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import openai4s.kernel.manager as manager_module
from openai4s.kernel import Kernel, font_cache
from openai4s.security.sandbox import KernelSandbox, SandboxStatus

INTERPRETER = "/opt/example-env/bin/python"


@pytest.fixture(autouse=True)
def _isolated_font_cache_state(tmp_path, monkeypatch):
    """Font roots under tmp, and no build enabled or remembered across tests."""

    roots = [tmp_path / "fonts-system", tmp_path / "fonts-user"]
    for root in roots:
        root.mkdir()
    monkeypatch.setattr(font_cache, "_font_roots", lambda platform, home: roots)
    font_cache.disable_background_builds()
    font_cache._inflight.clear()
    font_cache._failed_at.clear()
    yield roots
    font_cache.disable_background_builds()
    font_cache._inflight.clear()
    font_cache._failed_at.clear()


def _fontlist(version: str = "3.11.0", **extra) -> str:
    return json.dumps(
        {
            "__class__": "FontManager",
            "_version": version,
            "_FontManager__default_weight": "normal",
            "default_size": None,
            "defaultFamily": {"ttf": "DejaVu Sans", "afm": "Helvetica"},
            "afmlist": [],
            "ttflist": [],
            **extra,
        }
    )


def _builder_runner(payload: dict | None = None, *, calls: list | None = None):
    if payload is None:
        payload = {"name": "fontlist-v3.11.0.json", "content": _fontlist()}

    def run(command, **kwargs):
        if calls is not None:
            calls.append((list(command), kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "noise\n" + font_cache._MARKER + json.dumps(payload) + "\n"
            ).encode(),
            stderr=b"",
        )

    return run


def _enforced_sandbox(tmp_path: Path, name: str = "kernel") -> KernelSandbox:
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir()
    temp = tmp_path / f"{name}-temp"
    temp.mkdir(mode=0o700)
    status = SandboxStatus(
        mode="enforce",
        state="enabled",
        backend="seatbelt",
        enforced=True,
        self_test_passed=True,
        network_policy="blocked",
        workspace=str(workspace),
        temp_dir=str(temp),
        detail="offline test sandbox",
    )
    return KernelSandbox(
        status=status,
        executable="/usr/bin/sandbox-exec",
        temp_dir=str(temp),
        owns_temp_dir=True,
    )


def _kernel_mplconfigdir(sandbox: KernelSandbox) -> Path:
    return Path(sandbox.apply_environment({})["MPLCONFIGDIR"])


def test_an_enforced_kernel_is_seeded_with_the_host_built_font_list(tmp_path):
    data_dir = tmp_path / "data"
    calls: list = []
    built = font_cache.build_font_cache(
        INTERPRETER, data_dir=data_dir, runner=_builder_runner(calls=calls)
    )
    assert built is not None and built.name == "fontlist-v3.11.0.json"
    # The host ran the kernel's own interpreter, isolated, on a fixed program.
    assert calls[0][0][:3] == [INTERPRETER, "-I", "-c"]
    assert calls[0][0][3] == font_cache._BUILDER

    sandbox = _enforced_sandbox(tmp_path)
    try:
        assert font_cache.seed_kernel_font_cache(
            sandbox, interpreter=INTERPRETER, data_dir=data_dir
        )
        seeded = _kernel_mplconfigdir(sandbox) / "fontlist-v3.11.0.json"
        assert seeded.read_text(encoding="utf-8") == built.read_text(encoding="utf-8")
        assert not seeded.is_symlink()
    finally:
        sandbox.close()


def test_a_font_list_a_kernel_wrote_never_reaches_another_kernel(tmp_path):
    data_dir = tmp_path / "data"
    built = font_cache.build_font_cache(
        INTERPRETER, data_dir=data_dir, runner=_builder_runner()
    )
    assert built is not None
    trusted = built.read_bytes()

    first = _enforced_sandbox(tmp_path, "first")
    assert font_cache.seed_kernel_font_cache(
        first, interpreter=INTERPRETER, data_dir=data_dir
    )
    # A Cell in the first kernel rewrites its own copy -- a poisoned list, and
    # a fresh one for a matplotlib version the host never built.
    own = _kernel_mplconfigdir(first)
    (own / "fontlist-v3.11.0.json").write_text(
        _fontlist(ttflist=[{"fname": "/etc/passwd"}]), encoding="utf-8"
    )
    (own / "fontlist-v9.9.9.json").write_text(_fontlist("9.9.9"), encoding="utf-8")
    first.close()

    second = _enforced_sandbox(tmp_path, "second")
    try:
        assert font_cache.seed_kernel_font_cache(
            second, interpreter=INTERPRETER, data_dir=data_dir
        )
        theirs = _kernel_mplconfigdir(second)
        assert sorted(path.name for path in theirs.iterdir()) == [
            "fontlist-v3.11.0.json"
        ]
        assert (theirs / "fontlist-v3.11.0.json").read_bytes() == trusted
    finally:
        second.close()
    assert built.read_bytes() == trusted
    assert sorted(path.name for path in built.parent.iterdir()) == [
        "fontlist-v3.11.0.json",
        "manifest.json",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "../fontlist-v3.11.0.json", "content": _fontlist()},
        {"name": "fontlist-v3.11.0.json", "content": _fontlist("3.10.0")},
        {
            "name": "fontlist-v3.11.0.json",
            "content": json.dumps({"__class__": "FontEntry", "_version": "3.11.0"}),
        },
        {"name": "fontlist-v3.11.0.json", "content": "{not json"},
        {"name": "fontlist-v3.11.0.json", "content": _fontlist(pad="x" * 4096)},
        {"error": "ModuleNotFoundError"},
    ],
    ids=[
        "path",
        "version-mismatch",
        "not-a-fontmanager",
        "not-json",
        "oversize",
        "error",
    ],
)
def test_builder_output_that_is_not_a_font_list_is_not_stored(
    tmp_path, monkeypatch, payload
):
    monkeypatch.setattr(font_cache, "MAX_FONTLIST_BYTES", 1024)
    data_dir = tmp_path / "data"
    assert (
        font_cache.build_font_cache(
            INTERPRETER, data_dir=data_dir, runner=_builder_runner(payload)
        )
        is None
    )
    assert not (data_dir / "cache").exists()


def test_a_newly_installed_font_stops_the_stale_list_being_seeded(
    tmp_path, _isolated_font_cache_state
):
    data_dir = tmp_path / "data"
    assert font_cache.build_font_cache(
        INTERPRETER, data_dir=data_dir, runner=_builder_runner()
    )
    user_fonts = _isolated_font_cache_state[1]
    (user_fonts / "NotoSansCJK.otf").write_bytes(b"font")
    # Pin a different mtime explicitly: a coarse filesystem clock must not be
    # what decides whether this test can see the install.
    os.utime(user_fonts, ns=(1_000_000_000, 1_000_000_000))

    sandbox = _enforced_sandbox(tmp_path)
    try:
        assert not font_cache.seed_kernel_font_cache(
            sandbox, interpreter=INTERPRETER, data_dir=data_dir
        )
        assert not _kernel_mplconfigdir(sandbox).exists()
    finally:
        sandbox.close()


def test_a_cache_inside_the_kernels_own_workspace_is_not_trusted(tmp_path):
    sandbox = _enforced_sandbox(tmp_path)
    data_dir = Path(sandbox.status.workspace) / "data"
    assert font_cache.build_font_cache(
        INTERPRETER, data_dir=data_dir, runner=_builder_runner()
    )
    try:
        assert not font_cache.seed_kernel_font_cache(
            sandbox, interpreter=INTERPRETER, data_dir=data_dir
        )
        assert not _kernel_mplconfigdir(sandbox).exists()
    finally:
        sandbox.close()


def test_a_symlinked_cache_file_is_not_followed(tmp_path):
    data_dir = tmp_path / "data"
    built = font_cache.build_font_cache(
        INTERPRETER, data_dir=data_dir, runner=_builder_runner()
    )
    assert built is not None
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_bytes(built.read_bytes())
    built.unlink()
    built.symlink_to(elsewhere)

    sandbox = _enforced_sandbox(tmp_path)
    try:
        assert not font_cache.seed_kernel_font_cache(
            sandbox, interpreter=INTERPRETER, data_dir=data_dir
        )
    finally:
        sandbox.close()


def test_an_unconfined_kernel_keeps_its_shared_runtime_cache(tmp_path):
    data_dir = tmp_path / "data"
    assert font_cache.build_font_cache(
        INTERPRETER, data_dir=data_dir, runner=_builder_runner()
    )
    status = SandboxStatus(
        mode="off",
        state="disabled",
        backend=None,
        enforced=False,
        self_test_passed=None,
        network_policy="not_enforced",
        workspace=str(tmp_path),
        temp_dir=None,
        detail="off",
    )
    assert not font_cache.seed_kernel_font_cache(
        KernelSandbox(status=status), interpreter=INTERPRETER, data_dir=data_dir
    )


def test_builds_only_start_where_enabled_and_run_once_at_a_time(tmp_path):
    data_dir = tmp_path / "data"
    sandbox = _enforced_sandbox(tmp_path)
    calls: list = []
    release = threading.Event()
    build = _builder_runner()

    def slow_builder(command, **kwargs):
        calls.append(list(command))
        release.wait(10)
        return build(command, **kwargs)

    try:
        # Not enabled (a CLI one-shot, a test): a cache miss starts nothing.
        assert not font_cache.seed_kernel_font_cache(
            sandbox, interpreter=INTERPRETER, data_dir=data_dir, runner=slow_builder
        )
        assert font_cache.request_build(INTERPRETER, runner=slow_builder) is None
        assert calls == []

        font_cache.enable_background_builds(data_dir)
        thread = font_cache.request_build(INTERPRETER, runner=slow_builder)
        assert thread is not None
        # A second spawn while the first build is still scanning joins nothing.
        assert font_cache.request_build(INTERPRETER, runner=slow_builder) is None
        release.set()
        thread.join(10)
        assert not thread.is_alive()
        assert len(calls) == 1
        assert font_cache.seed_kernel_font_cache(sandbox, interpreter=INTERPRETER)
    finally:
        release.set()
        sandbox.close()


def test_a_failed_build_is_not_retried_on_every_spawn(tmp_path):
    font_cache.enable_background_builds(tmp_path / "data")
    calls: list = []
    runner = _builder_runner({"error": "ModuleNotFoundError"}, calls=calls)
    thread = font_cache.request_build(INTERPRETER, runner=runner)
    assert thread is not None
    thread.join(10)
    assert font_cache.request_build(INTERPRETER, runner=runner) is None
    assert len(calls) == 1


def _fake_matplotlib(root: Path) -> Path:
    package = root / "matplotlib"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "import os\n" "def get_cachedir():\n" "    return os.environ['MPLCONFIGDIR']\n",
        encoding="utf-8",
    )
    (package / "font_manager.py").write_text(
        "import json, os\n"
        "import matplotlib\n"
        "class FontManager:\n"
        "    __version__ = '3.11.0'\n"
        "path = os.path.join(matplotlib.get_cachedir(), 'fontlist-v3.11.0.json')\n"
        "with open(path, 'w', encoding='utf-8') as handle:\n"
        f"    handle.write({_fontlist()!r})\n",
        encoding="utf-8",
    )
    return root


def test_the_builder_program_returns_the_list_matplotlib_wrote(tmp_path):
    """The fixed program the host runs, against a stand-in matplotlib.

    `-I` is dropped only so the stand-in is importable; the program is the
    one production runs, and it must hand back what the font manager wrote
    into the fresh directory it created -- not a pre-existing cache.
    """

    fake = _fake_matplotlib(tmp_path / "site")
    stale = tmp_path / "stale-shared-cache"
    stale.mkdir()
    (stale / "fontlist-v3.11.0.json").write_text("poison", encoding="utf-8")

    def runner(command, *, timeout):
        assert command[1] == "-I"
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(fake),
            "MPLCONFIGDIR": str(stale),
            "TMPDIR": str(tmp_path),
        }
        return subprocess.run(
            [command[0], *command[2:]],
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )

    built = font_cache.build_font_cache(
        sys.executable, data_dir=tmp_path / "data", runner=runner
    )
    assert built is not None
    assert json.loads(built.read_text(encoding="utf-8"))["__class__"] == "FontManager"
    assert "poison" not in built.read_text(encoding="utf-8")


def test_a_python_kernel_asks_for_its_font_list_with_its_own_sandbox(
    tmp_path, monkeypatch
):
    seeded: list = []
    monkeypatch.setattr(
        manager_module,
        "seed_kernel_font_cache",
        lambda sandbox, *, interpreter: seeded.append((sandbox, interpreter)),
    )
    with Kernel(cwd=str(tmp_path)) as kernel:
        assert kernel.execute("x = 1")["error"] is None
        assert seeded == [(kernel._sandbox, sys.executable)]


def _font_manager_version() -> str | None:
    spec = importlib.util.find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        return None
    source = Path(list(spec.submodule_search_locations)[0]) / "font_manager.py"
    match = re.search(
        r"^\s+__version__\s*=\s*['\"]([^'\"]+)['\"]",
        source.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def test_a_sandboxed_kernel_uses_the_seeded_list_instead_of_scanning(
    tmp_path, monkeypatch
):
    """End to end on a host where the sandbox is really enforced.

    The host list is deliberately empty. A kernel that loads it reports zero
    fonts at once; a kernel that ignored it would scan the system (seconds,
    and a non-empty list). Skipped where no sandbox is enforced, since an
    unconfined kernel keeps the shared runtime cache instead.
    """

    version = _font_manager_version()
    if version is None:
        pytest.skip("matplotlib is not installed")
    data_dir = Path(os.environ["OPENAI4S_DATA_DIR"])
    payload = {"name": f"fontlist-v{version}.json", "content": _fontlist(version)}
    assert font_cache.build_font_cache(
        sys.executable, data_dir=data_dir, runner=_builder_runner(payload)
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with Kernel(cwd=str(workspace)) as kernel:
        if not kernel.sandbox_status.get("enforced"):
            pytest.skip("no enforced kernel sandbox on this host")
        result = kernel.execute(
            "from matplotlib import font_manager\n"
            "print(len(font_manager.fontManager.ttflist))"
        )

    assert result["error"] is None
    assert result["stdout"].strip() == "0"
