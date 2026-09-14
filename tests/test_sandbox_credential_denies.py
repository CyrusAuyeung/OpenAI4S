"""Which credentials an enforced kernel sandbox actually keeps from a cell.

Two gaps, both measured against a real enforced sandbox on macOS rather than
inferred from the profile text.

**The daemon's access token.** The deny list carried
`("prefix", data_dir / "openai4s.db")`, and the token is a *sibling* of the
database, not a prefix of it — so the DB was blocked and the token was read.
That token gates the whole HTTP API, so a cell holding it can drive every route
the daemon serves, including the ones that execute code.

**The macOS keychain.** `OPENAI4S_SECRET_STORE` defaults to the keychain on
macOS, so the LLM API key lives there, and a cell could run `/usr/bin/security`
and reach it — `security list-keychains` returned the user's keychain path from
inside the sandbox.

Denying the keychain *files* alone does not close that: `securityd` is a
separate daemon that opens them on the caller's behalf, so file rules never
apply to it. The `mach-lookup` denies are what work. The file denies stay too,
because a readable keychain database can be attacked offline.

The obvious worry was TLS — on macOS the Security framework validates
certificates, so cutting off securityd might break every HTTPS fetch a science
cell makes. Measured under exactly these rules: `security list-keychains`
fails while `curl` and `urllib` both return 200. And inside the kernel, HTTPS
fails identically with and without these rules, because the sandbox's own
`(deny network*)` is what stops it — a different policy, deliberately.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from openai4s.security import sandbox


def _profile(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI4S_DATA_DIR", str(tmp_path / "data"))
    return sandbox.build_seatbelt_profile(
        str(tmp_path / "ws"),
        str(tmp_path / "tmp"),
        deny_read=sandbox._default_secret_read_denials(str(tmp_path / "ws")),
        allow_raw_network=False,
    )


def test_the_access_token_is_denied_by_name_not_by_luck(tmp_path, monkeypatch):
    """The defect. A prefix rule on `openai4s.db` does not cover a sibling."""
    entries = dict((path, kind) for kind, path in _deny_entries(monkeypatch, tmp_path))
    token = str((tmp_path / "data" / "access-token").resolve())
    assert token in entries, "the daemon's access token is not in the deny list"


def test_the_database_is_still_denied(tmp_path, monkeypatch):
    """Adding an entry must not have displaced the one that was there."""
    paths = [path for _kind, path in _deny_entries(monkeypatch, tmp_path)]
    assert any(path.endswith("openai4s.db") for path in paths)


def test_share_credentials_are_denied(tmp_path, monkeypatch):
    """A share's tokens are what make a read-only snapshot reachable from off
    this machine, so they belong beside the access token rather than one
    directory away from it."""
    paths = [path for _kind, path in _deny_entries(monkeypatch, tmp_path)]
    assert any(path.rstrip("/").endswith("shares") for path in paths)


def _deny_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI4S_DATA_DIR", str(tmp_path / "data"))
    return sandbox._default_secret_read_denials(str(tmp_path / "ws"))


# --------------------------------------------------------------------------
# the default ~/.openai4s instance, when OPENAI4S_DATA_DIR points elsewhere
# --------------------------------------------------------------------------
#
# The deny list was built from a single data dir: OPENAI4S_DATA_DIR if set,
# else ~/.openai4s. So a CLI run, benchmark, test or second daemon pointed at a
# redirected data dir left the default instance's access-token, bootstrap
# secret, shares and DB fully readable to an enforced cell -- credentials that
# are exactly as sensitive whichever instance owns them.


def _deny_paths_with_redirected_data_dir(monkeypatch, tmp_path):
    """The deny paths when OPENAI4S_DATA_DIR is redirected away from ~."""
    home = tmp_path / "home"
    (home / ".openai4s").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENAI4S_DATA_DIR", str(tmp_path / "data"))
    entries = sandbox._default_secret_read_denials(str(tmp_path / "ws"))
    return home, {path for _kind, path in entries}


def test_the_default_instance_secrets_are_denied_too(tmp_path, monkeypatch):
    """The defect. With OPENAI4S_DATA_DIR redirected, the well-known default
    ~/.openai4s instance's credentials must still be denied -- not just the
    configured data dir's."""
    home, paths = _deny_paths_with_redirected_data_dir(monkeypatch, tmp_path)
    default = (home / ".openai4s").resolve()
    for name in ("access-token", "worker-bootstrap-secret", "shares"):
        assert str(default / name) in paths, f"default instance {name} not denied"
    # The DB is a prefix entry, so it is stored as the db path itself.
    assert any(
        p == str(default / "openai4s.db") for p in paths
    ), "default instance database not denied"


def test_the_configured_data_dir_is_still_denied(tmp_path, monkeypatch):
    """Covering the default instance must not drop the configured one."""
    _home, paths = _deny_paths_with_redirected_data_dir(monkeypatch, tmp_path)
    configured = (tmp_path / "data").resolve()
    assert str(configured / "access-token") in paths
    assert any(p == str(configured / "openai4s.db") for p in paths)


@pytest.mark.parametrize("spelling", ("verbatim", "symlink"))
def test_the_default_instance_is_not_double_listed(tmp_path, monkeypatch, spelling):
    """When OPENAI4S_DATA_DIR *names* ~/.openai4s the configured and default
    passes describe one instance, and each rule must be emitted once.

    Both spellings reach the de-duplication: the variable set to the default
    path itself, and to a symlink that only `resolve()` recognises as it. With
    the variable unset only one pass runs, so that case could not tell a
    de-duplicating list from one that does not de-duplicate at all.
    """
    home = tmp_path / "home"
    default = home / ".openai4s"
    default.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    if spelling == "symlink":
        alias = tmp_path / "data-dir-alias"
        alias.symlink_to(default, target_is_directory=True)
        monkeypatch.setenv("OPENAI4S_DATA_DIR", str(alias))
    else:
        monkeypatch.setenv("OPENAI4S_DATA_DIR", str(default))
    entries = sandbox._default_secret_read_denials(str(tmp_path / "ws"))
    paths = [path for _kind, path in entries]
    token = str((default / "access-token").resolve())
    assert paths.count(token) == 1, "the default instance token is listed twice"


# --------------------------------------------------------------------------
# the macOS process-info / KERN_PROCARGS read channel
# --------------------------------------------------------------------------
#
# Seatbelt opens with `(allow default)`, so a cell could read another process's
# argument/environment block through `sysctl(CTL_KERN, KERN_PROCARGS2, <pid>)`.
# That is where a daemon whose LLM key is configured by environment variable /
# .env holds it in cleartext. bubblewrap masks /proc/<daemon>/environ on Linux
# for the same reason (`test_the_daemon_environ_is_masked_on_linux`); the
# Seatbelt profile had no analog. The two denies are the Seatbelt-side narrowing
# -- and BOTH are required: for a detached (setsid) target, which the daemon is,
# the kernel gates KERN_PROCARGS2 behind both the process-info class and the
# kern.proc sysctl name and passing *either* allows the read, so neither deny
# alone closes it (measured on macOS 26.x; the behavioural test below asserts
# the closure directly).


def test_the_profile_denies_the_process_info_channel(tmp_path, monkeypatch):
    """The defect. The profile must deny the process-info introspection class
    and the kern.proc sysctl name so a cell cannot walk other processes."""
    profile = _profile(tmp_path, monkeypatch)
    assert "process-info" in profile, "no process-info deny in the profile"
    assert 'sysctl-name-prefix "kern.proc"' in profile, "no kern.proc sysctl deny"


def test_the_process_info_denies_come_after_allow_default(tmp_path, monkeypatch):
    """SBPL is last-match-wins. A deny before `(allow default)` is silently
    permissive, exactly the trap the keychain test guards."""
    profile = _profile(tmp_path, monkeypatch)
    lines = profile.splitlines()
    allow_default = lines.index("(allow default)")
    for needle in ("process-info", "kern.proc"):
        placed = [i for i, line in enumerate(lines) if needle in line]
        assert placed, f"{needle} is not in the profile"
        assert min(placed) > allow_default, f"{needle} is overridden by allow default"


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_the_process_info_denies_do_not_break_a_real_cell(tmp_path, monkeypatch):
    """The reason this deny could have been the wrong trade — mirroring the
    keychain/TLS test above.

    `(deny process-info* ...)` and the `kern.proc` sysctl deny could plausibly
    break a science cell: `os.uname` and `os.cpu_count` read sysctls at startup,
    and spawning a child interpreter touches process management. Measured under
    the real profile rather than assumed. (This is behavioural on purpose:
    `auto` degrading silently is a documented concern here, so the claim that
    the profile *loads and takes effect without breaking the cell* has to be an
    assertion about a real sandboxed process, not about the profile text.)
    """
    import subprocess

    profile = _profile(tmp_path, monkeypatch)
    written = tmp_path / "procinfo-profile.sb"
    written.write_text(profile, encoding="utf-8")
    (tmp_path / "ws").mkdir(exist_ok=True)
    (tmp_path / "tmp").mkdir(exist_ok=True)

    cell = (
        "import os, sys, subprocess;"
        "u = os.uname();"
        "child = subprocess.run([sys.executable, '-c', 'print(6*7)'],"
        " capture_output=True, text=True, timeout=30);"
        "print('OK', u.sysname, os.cpu_count() or 0, child.stdout.strip())"
    )
    result = subprocess.run(
        ["sandbox-exec", "-f", str(written), sys.executable, "-c", cell],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, (
        "the process-info denies broke a legitimate cell: "
        f"rc={result.returncode} stderr={result.stderr[:300]}"
    )
    out = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert out.startswith("OK Darwin"), f"os.uname failed under the profile: {out!r}"
    assert out.endswith("42"), f"subprocess child failed under the profile: {out!r}"


# The reader that mounts the exploit: sysctl(CTL_KERN=1, KERN_PROCARGS2=49, pid)
# and report whether the marker env var was recovered from the target's block.
_PROCARGS_READER = r"""
import ctypes, ctypes.util, os, re, sys
pid = int(sys.argv[1])
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
mib = (ctypes.c_int * 3)(1, 49, pid)
size = ctypes.c_size_t(0)
if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or not size.value:
    print("BLOCKED", ctypes.get_errno()); raise SystemExit
buf = ctypes.create_string_buffer(size.value)
if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
    print("BLOCKED", ctypes.get_errno()); raise SystemExit
parts = [p for p in buf.raw[: size.value].split(b"\0")
         if re.match(rb"^[A-Za-z_][A-Za-z0-9_]*=", p)]
print("RECOVERED" if any(p.startswith(b"SANDBOX_MARKER_ENV=") for p in parts)
      else "ABSENT", len(parts))
"""

# A detached session leader that parks with a marker env var, standing in for
# the `setsid` daemon whose environment the exploit targets.
_MARKED_DAEMON = r"""
import os, sys, time
if os.fork() > 0:
    os._exit(0)
os.setsid()
if os.fork() > 0:
    os._exit(0)
open(sys.argv[1], "w").write(str(os.getpid()))
time.sleep(60)
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_a_sandboxed_cell_cannot_read_a_daemons_environ(tmp_path, monkeypatch):
    """The macOS analog of `test_the_daemon_environ_is_masked_on_linux`.

    A detached (`setsid`) sibling holds a marker env var, exactly where the
    daemon holds an env/.env LLM key. Verify against the real kernel — not the
    profile text — that a Seatbelt-wrapped reader cannot recover that marker
    through `sysctl(KERN_PROCARGS2)`, and that an *unsandboxed* reader can (so
    the assertion is about the sandbox, not about the marker being absent).
    """
    import subprocess

    reader = tmp_path / "reader.py"
    reader.write_text(_PROCARGS_READER, encoding="utf-8")
    spawner = tmp_path / "daemon.py"
    spawner.write_text(_MARKED_DAEMON, encoding="utf-8")
    pidfile = tmp_path / "daemon.pid"

    env = {**os.environ, "SANDBOX_MARKER_ENV": "sandbox-marker-value"}
    subprocess.run([sys.executable, str(spawner), str(pidfile)], env=env, timeout=30)
    for _ in range(100):
        if pidfile.exists():
            break
        time.sleep(0.05)
    assert pidfile.exists(), "the marked daemon did not start"
    daemon_pid = int(pidfile.read_text().strip())
    try:
        # Control: without the sandbox the marker IS recoverable, so a later
        # ABSENT really means the sandbox blocked the read.
        control = subprocess.run(
            [sys.executable, str(reader), str(daemon_pid)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert control.stdout.split()[0] == "RECOVERED", (
            "control read did not recover the marker; the test would be "
            f"vacuous: {control.stdout!r} {control.stderr[:200]!r}"
        )

        profile = _profile(tmp_path, monkeypatch)
        written = tmp_path / "profile.sb"
        written.write_text(profile, encoding="utf-8")
        (tmp_path / "ws").mkdir(exist_ok=True)
        (tmp_path / "tmp").mkdir(exist_ok=True)
        sandboxed = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(written),
                sys.executable,
                str(reader),
                str(daemon_pid),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        verdict = sandboxed.stdout.split()[0] if sandboxed.stdout.split() else ""
        assert verdict != "RECOVERED", (
            "a Seatbelt-wrapped cell recovered the daemon's environment via "
            f"KERN_PROCARGS2: {sandboxed.stdout!r} {sandboxed.stderr[:200]!r}"
        )
        assert verdict in ("BLOCKED", "ABSENT"), (
            f"unexpected reader output under the sandbox: {sandboxed.stdout!r} "
            f"{sandboxed.stderr[:200]!r}"
        )
    finally:
        try:
            os.kill(daemon_pid, 9)
        except ProcessLookupError:
            pass


# --------------------------------------------------------------------------
# the keychain
# --------------------------------------------------------------------------


def test_the_profile_cuts_off_securityd_not_just_the_keychain_files(
    tmp_path, monkeypatch
):
    """The file rules are not what closes this. `securityd` opens the keychain
    on the caller's behalf, so only refusing to reach it works."""
    profile = _profile(tmp_path, monkeypatch)
    assert 'deny mach-lookup (global-name "com.apple.SecurityServer")' in profile
    assert 'deny mach-lookup (global-name "com.apple.securityd.xpc")' in profile
    # ...and the database itself stays unreadable, for an offline attacker.
    assert "/Library/Keychains" in profile


def test_the_denies_come_after_allow_default(tmp_path, monkeypatch):
    """SBPL is last-match-wins. A deny placed before `(allow default)` is not a
    deny at all, and the profile would still load — silently permissive."""
    profile = _profile(tmp_path, monkeypatch)
    lines = profile.splitlines()
    allow_default = lines.index("(allow default)")
    for needle in ("com.apple.SecurityServer", "/Library/Keychains"):
        placed = [i for i, line in enumerate(lines) if needle in line]
        assert placed, f"{needle} is not in the profile"
        assert min(placed) > allow_default, f"{needle} is overridden by allow default"


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_a_sandboxed_process_really_cannot_reach_the_keychain(tmp_path, monkeypatch):
    """Against the real kernel, not the profile text.

    A profile that reads correctly and does not take effect is the failure this
    is here to catch — `auto` degrading silently is a documented concern in
    this codebase, so the assertion has to be about behaviour.
    """
    import subprocess

    profile = _profile(tmp_path, monkeypatch)
    written = tmp_path / "profile.sb"
    written.write_text(profile, encoding="utf-8")
    (tmp_path / "ws").mkdir(exist_ok=True)
    (tmp_path / "tmp").mkdir(exist_ok=True)

    result = subprocess.run(
        ["sandbox-exec", "-f", str(written), "/usr/bin/security", "list-keychains"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        result.returncode != 0 or not result.stdout.strip()
    ), f"the keychain was reachable from inside the sandbox: {result.stdout[:200]}"


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is macOS-only")
def test_certificate_validation_still_works_under_the_same_rules(tmp_path, monkeypatch):
    """The reason this fix could have been the wrong trade. On macOS the
    Security framework validates certificates, so cutting off securityd might
    have broken every HTTPS fetch a science cell makes. It does not — but the
    claim is worth a test rather than a comment, because the day it stops being
    true this is how anyone finds out.
    """
    import subprocess

    profile = _profile(tmp_path, monkeypatch)
    # Raw network is denied in the kernel profile by design; this test is about
    # the keychain rules specifically, so it allows network and changes nothing
    # else.
    profile = profile.replace("(deny network*)\n", "")
    written = tmp_path / "net-profile.sb"
    written.write_text(profile, encoding="utf-8")
    (tmp_path / "ws").mkdir(exist_ok=True)
    (tmp_path / "tmp").mkdir(exist_ok=True)

    result = subprocess.run(
        [
            "sandbox-exec",
            "-f",
            str(written),
            sys.executable,
            "-c",
            "import urllib.request;"
            "print(urllib.request.urlopen('https://example.com', timeout=20).status)",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0 and "urlopen error" in result.stderr:
        pytest.skip(f"no outbound network here: {result.stderr.strip()[:120]}")
    assert result.stdout.strip() == "200", (
        f"TLS broke under the keychain denies: rc={result.returncode} "
        f"stderr={result.stderr[:200]}"
    )


# --------------------------------------------------------------------------
# the Linux branch, forced
# --------------------------------------------------------------------------


def _bwrap(monkeypatch, tmp_path, *, fake_proc=True):
    """Build the bwrap argv with the Linux branch forced.

    Development here is macOS, so `/proc` does not exist and the branch under
    test is never taken by accident. Forcing it is the only way this is checked
    at all before a Linux run — the divergence CLAUDE.md warns about.
    """
    monkeypatch.setattr(sandbox.wsl, "is_wsl", lambda: False)
    if fake_proc:
        real_exists = os.path.exists
        monkeypatch.setattr(
            sandbox.os.path,
            "exists",
            lambda p: True if str(p).startswith("/proc/") else real_exists(p),
        )
    return sandbox.wrap_bwrap_command(
        ["python3", "-c", "1"],
        executable="/usr/bin/bwrap",
        workspace=str(tmp_path / "ws"),
        temp_dir=str(tmp_path / "tmp"),
        allow_raw_network=False,
        deny_read=(),
    )


def test_the_daemon_environ_is_masked_on_linux(tmp_path, monkeypatch):
    """The part of the PID-namespace gap that carries the credentials.

    The sandbox keeps the host PID namespace on purpose so the manager can
    validate bubblewrap's direct worker child before interrupting it. `/proc`
    therefore still shows the daemon, and the daemon's environment is where
    the API keys are, since the child's own environment is allowlisted clean.
    """
    argv = _bwrap(monkeypatch, tmp_path)
    environ = f"/proc/{os.getpid()}/environ"
    assert environ in argv, "the daemon's environment is readable from a cell"
    assert argv[argv.index(environ) - 1] == "/dev/null"
    assert argv[argv.index(environ) - 2] == "--ro-bind"


def test_the_mask_comes_after_the_proc_mount(tmp_path, monkeypatch):
    """Order is the whole thing. `--proc /proc` mounts a fresh procfs, so a
    bind placed before it is replaced and the mask silently does nothing."""
    argv = _bwrap(monkeypatch, tmp_path)
    environ = f"/proc/{os.getpid()}/environ"
    assert argv.index("--proc") < argv.index(environ)


def test_the_mask_is_before_the_command_separator(tmp_path, monkeypatch):
    """Everything after `--` is the command, not bwrap's own arguments."""
    argv = _bwrap(monkeypatch, tmp_path)
    environ = f"/proc/{os.getpid()}/environ"
    assert argv.index(environ) < argv.index("--")


def test_nothing_is_emitted_where_there_is_no_proc(tmp_path, monkeypatch):
    """A bind to a path that does not exist makes bwrap refuse to start, which
    would take the kernel down on any platform without /proc."""
    argv = _bwrap(monkeypatch, tmp_path, fake_proc=False)
    if not Path("/proc").exists():
        assert not any("/environ" in str(arg) for arg in argv)


def test_the_pid_namespace_stays_shared_on_purpose(tmp_path, monkeypatch):
    """Recorded as a decision rather than left implicit. `--unshare-pid` makes
    bwrap interpose an additional init/reaper; the current interrupt resolver
    instead validates the direct child in the shared procfs. Closing the rest
    of this gap therefore needs an explicit child-pid channel. What is left
    open is that a cell can see other processes exist; what is closed is the
    one file that carries credentials.
    """
    argv = _bwrap(monkeypatch, tmp_path)
    assert "--unshare-pid" not in argv
    assert "--unshare-ipc" in argv and "--unshare-uts" in argv
