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
