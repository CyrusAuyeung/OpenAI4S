"""Release documentation must describe the release machinery that exists.

The docs a maintainer follows when cutting a release, and the docs a user
follows when installing one, are prose. Prose is the one thing no workflow
executes, so it drifted from `.github/workflows/release.yml` without any gate
noticing:

* `docs/release-validation.md` told maintainers to "publish the GitHub Release"
  for the tag. `release.yml` is dispatch-only and draft-first. A maintainer who
  did what the doc said made the release public before the pipeline ran, so the
  guard refused to stage onto it. The only mode left was `pypi_only`, which
  attaches nothing, and that is how v0.2.0's GitHub Release ended up with no
  wheel, sdist, SBOM, provenance or evidence bundle.

Every check here reads a fact from the machinery (the workflow file, the
version declaration) and a claim from the docs, and fails when they disagree.
The phrases are matched after whitespace normalisation, so rewrapping a
paragraph cannot hide one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELEASE_VALIDATION = ROOT / "docs" / "release-validation.md"
CONTRIBUTING = ROOT / ".github" / "CONTRIBUTING.md"


def _normalised(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _section(path: Path, heading: str) -> str:
    """The body of one `## ` section, up to the next `## ` heading."""
    text = path.read_text(encoding="utf-8")
    start = text.index(f"\n{heading}\n")
    end = text.find("\n## ", start + len(heading) + 2)
    return text[start : end if end != -1 else len(text)]


def _project_version() -> str:
    # Not tomllib: the suite also runs on Python 3.10.
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert match, "pyproject.toml no longer declares a project version"
    return match.group(1)


# -- trusted publication is draft-first --------------------------------------


def test_the_release_docs_never_tell_a_maintainer_to_publish_the_release_by_hand():
    """Each phrase is an instruction that makes the release public before the
    workflow runs, which `release.yml`'s guard then refuses to stage onto."""
    forbidden = (
        "publish the GitHub Release for that tag",
        "from a non-prerelease GitHub Release.",
        "GitHub Release whose tag starts with `v` builds",
        "Publication needs an approved GitHub Release",
    )
    for path in (RELEASE_VALIDATION, CONTRIBUTING):
        text = _normalised(path)
        present = [phrase for phrase in forbidden if phrase in text]
        assert not present, f"{path.relative_to(ROOT)} still says {present}"


def test_trusted_publication_spells_out_the_draft_first_dispatch():
    """The section a maintainer reads must name the commands the workflow
    actually needs: an annotated tag, a draft that is verified against that
    tag, and a `publish=true` dispatch against the tag ref."""
    section = " ".join(_section(RELEASE_VALIDATION, "## Trusted publication").split())
    for needed in (
        "git tag -a vX.Y.Z",
        "gh release create vX.Y.Z --draft --verify-tag",
        "gh workflow run release.yml --ref vX.Y.Z -f tag=vX.Y.Z -f publish=true",
        "Never publish the GitHub Release by hand.",
        "`pypi_only` exists only to recover",
    ):
        assert needed in section, f"Trusted publication no longer says {needed!r}"


def test_the_workflow_really_is_dispatch_only_and_draft_first():
    """The two facts the doc tests above rely on. If the workflow changes,
    these fail first, and the doc has to be rewritten to match."""
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    trigger = workflow.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert re.search(r"^  workflow_dispatch:$", trigger, re.MULTILINE)
    assert not re.search(
        r"^  (release|push):", trigger, re.MULTILINE
    ), "release.yml is triggered by an event again, not only by a dispatch"
    assert "is already public; staging assets onto it" in workflow


def test_concrete_version_examples_match_the_tree_or_are_placeholders():
    """`verify_release_tag.py v0.1.0` exits 1 against any later tree, so a
    stale example is a command that fails when copied. An example either names
    the version this tree declares or uses the `X.Y.Z` placeholder."""
    text = RELEASE_VALIDATION.read_text(encoding="utf-8")
    version = _project_version()
    patterns = (
        r"verify_release_tag\.py v(\d+\.\d+\.\d+)",
        r"release_pipeline\.py --version (\d+\.\d+\.\d+)",
        r"openai4s-(\d+\.\d+\.\d+)-evidence\.zip",
    )
    stale = [
        match.group(0)
        for pattern in patterns
        for match in re.finditer(pattern, text)
        if match.group(1) != version
    ]
    assert not stale, (
        f"docs/release-validation.md has version examples that are not "
        f"{version} and not a placeholder: {stale}"
    )


# -- upgrading from 0.2.x ------------------------------------------------------

UPGRADING = ROOT / "docs" / "upgrading.md"
UPGRADING_ZH = ROOT / "docs" / "upgrading_zh.md"
MIGRATIONS = ROOT / "openai4s" / "storage" / "migrations.py"

#: The schema the published 0.2.0 wheel creates. A fact about a release that
#: already exists, so it is a constant rather than something read from the tree.
V020_SCHEMA = 27


def _migration_deletes_its_backup_on_success() -> bool:
    source = MIGRATIONS.read_text(encoding="utf-8")
    tail = source.split("Only now that the upgrade is committed", 1)
    return len(tail) == 2 and "backup.unlink()" in tail[1]


def test_the_future_schema_refusal_is_not_read_as_protecting_a_downgrade():
    """The refusal paragraph read as if a newer schema were always refused.
    0.2.0 predates the guard, opens a schema-32 database silently and writes to
    it, so the paragraph has to say which versions it covers and send a user
    who may roll back to a backup."""
    text = _normalised(RELEASE_VALIDATION)
    start = text.index("schema newer than this program supports")
    window = text[start : start + 1600]
    assert "0.2.0 and earlier do not check the schema version" in window
    assert "back up `<data_dir>/openai4s.db`" in window
    assert "upgrading.md" in window


def test_the_upgrade_guide_states_the_schema_change_the_backup_and_no_downgrade():
    """Both halves must tell a 0.2.x user the three things that cannot be
    undone by reinstalling: the schema moves, the migration's own copy is gone
    after success, and 0.2.x will not refuse the upgraded database."""
    current = int(
        re.search(r"^SCHEMA_VERSION = (\d+)$", MIGRATIONS.read_text("utf-8"), re.M)[1]
    )
    assert current >= 32, "the upgrade guide names a schema this tree does not reach"
    english = _normalised(UPGRADING)
    chinese = _normalised(UPGRADING_ZH)
    for text in (english, chinese):
        assert f"schema **{V020_SCHEMA}**" in text
        assert "schema **32**" in text
        assert f"openai4s.db.v{V020_SCHEMA}.bak" in text
        assert "cp -a ~/.openai4s ~/.openai4s-0.2-backup" in text
        assert "OPENAI4S_REQUIRE_TOKEN=0" in text
        assert "openai4s url" in text
    assert "Going back to 0.2.x is not supported" in english
    assert "不支持退回 0.2.x" in chinese
    # The claim about the backup is read from the code, not assumed: if a
    # migration starts keeping its pre-upgrade copy, this fails until both
    # halves stop telling users it is deleted.
    deletes = _migration_deletes_its_backup_on_success()
    assert deletes == ("deletes it once the migration succeeds" in english)
    assert deletes == ("迁移成功后会删除它" in chinese)


# -- what each platform can actually download ----------------------------------

WORKFLOWS = ROOT / ".github" / "workflows"
USER_INSTALL_DOCS = (
    ROOT / "README.md",
    ROOT / "README_zh.md",
    ROOT / "docs" / "startup-guide.md",
)


def _macos_asset_defaults_to_omit() -> bool:
    workflow = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    block = workflow.split("      macos_asset:", 1)
    return len(block) == 2 and bool(
        re.search(r"^        default: omit$", block[1].split("\n\n", 1)[0], re.M)
    )


def test_no_install_doc_sends_a_mac_user_to_the_latest_release_for_a_dmg():
    """While the release workflow omits the DMG by default, the latest release
    has no macOS asset. A `macos-arm64.dmg` named a few lines from a
    `releases/latest` link is a download that is not there. A proximity window
    rather than one line, because the two sat on adjacent wrapped lines."""
    if not _macos_asset_defaults_to_omit():
        pytest.skip("release.yml publishes a DMG by default again")
    offenders = []
    for path in USER_INSTALL_DOCS:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "releases/latest" not in line:
                continue
            window = lines[max(0, index - 3) : index + 4]
            if any("macos-arm64.dmg" in near for near in window):
                offenders.append(f"{path.relative_to(ROOT)}:{index + 1}")
    assert not offenders, f"DMG download pointed at the latest release: {offenders}"


def test_platforms_does_not_claim_a_notarized_dmg_ships():
    if not _macos_asset_defaults_to_omit():
        pytest.skip("release.yml publishes a DMG by default again")
    text = _normalised(ROOT / "docs" / "platforms.md")
    assert "macOS ships as a signed, notarized" not in text
    assert "v0.3.0 publishes no DMG" in text


def test_the_readmes_do_not_say_the_windows_package_ships_later():
    """`release.yml` stages the Windows zip on every publish; nothing can omit
    it. A README note saying the package ships in a coming release contradicts
    the release it is published with."""
    workflow = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "Download the verified Windows package" in workflow
    forbidden = {
        ROOT
        / "README.md": "Windows/WSL2 package is still stabilizing and ships in a coming release",
        ROOT / "README_zh.md": "Windows/WSL2 安装包仍在稳定化，将随后续版本发布",
    }
    for path, phrase in forbidden.items():
        assert phrase not in _normalised(path), f"{path.name} still defers Windows"


def test_platforms_names_the_published_container_image():
    if not (WORKFLOWS / "publish-image.yml").is_file():
        pytest.skip("no container image workflow")
    text = _normalised(ROOT / "docs" / "platforms.md")
    assert "No registry publishes it" not in text
    assert "ghcr.io/pku-yuangroup/openai4s" in text


def test_the_workflow_readmes_do_not_call_the_linux_boundary_smoke_manual():
    """`ci.yml` runs `harness.smoke.linux_sandbox` as its own job on every CI
    event, and the release receipt attests it. Calling it manual, or saying it
    is unproven "because it is not a current CI gate", describes a workflow
    that no longer exists."""
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    if "python -m harness.smoke.linux_sandbox" not in ci:
        pytest.skip("ci.yml no longer runs the full Linux boundary smoke")
    english = _normalised(WORKFLOWS / "README.md")
    chinese = _normalised(WORKFLOWS / "README_zh.md")
    assert "Linux boundary smoke remains manual" not in english
    assert "because it is not a current CI gate" not in english
    assert "仍需手动执行" not in chinese
    assert "不是当前 CI gate" not in chinese
    assert "ci-linux-sandbox-full" in english and "ci-linux-sandbox-full" in chinese
