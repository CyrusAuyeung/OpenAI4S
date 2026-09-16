"""The paper citation is written three times and must say the same thing.

The arXiv BibTeX sits in `README.md` and `README_zh.md`. `CITATION.cff`
carries the same paper as `preferred-citation`, which is what GitHub's "Cite
this repository" button renders. Nothing else reads any of the three, so an
author added to one copy and not the others would ship without complaint.

The CFF checks follow ruby-cff, the formatter GitHub uses:

* The `generic` reference type renders as `@misc`, the entry type the READMEs
  use.
* A `name:` author renders as one braced entity. "OpenAI4S Community" written
  as a person would come out as "Community, OpenAI4S".
* `repository-code` takes precedence over `url`. Inside `preferred-citation`
  it would replace the arXiv link with the repository link.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFF = ROOT / "CITATION.cff"
READMES = (ROOT / "README.md", ROOT / "README_zh.md")

_BIBTEX_BLOCK = re.compile(r"```bibtex\n(.*?)```", re.S)
_ENTRY_HEAD = re.compile(r"@(\w+)\{([^,\s]+),\s*$")
_FIELD = re.compile(r"^\s*(\w+)=\{(.*)\},?\s*$")


def _bibtex_block(readme: Path) -> str:
    blocks = _BIBTEX_BLOCK.findall(readme.read_text(encoding="utf-8"))
    assert len(blocks) == 1, f"{readme.name}: expected one bibtex block"
    return blocks[0]


def _parse_bibtex(block: str) -> tuple[str, str, dict[str, str]]:
    lines = [line for line in block.splitlines() if line.strip()]
    head = _ENTRY_HEAD.match(lines[0])
    assert head, f"unparsed entry head: {lines[0]!r}"
    assert lines[-1].strip() == "}", "entry must close on its own line"
    fields: dict[str, str] = {}
    for line in lines[1:-1]:
        field = _FIELD.match(line)
        assert field, f"unparsed bibtex field line: {line!r}"
        name, value = field.groups()
        assert name not in fields, f"duplicate bibtex field {name}"
        fields[name] = value
    return head.group(1), head.group(2), fields


def _render(author: dict) -> str:
    if "name" in author:
        return author["name"]
    return f"{author['given-names']} {author['family-names']}"


@pytest.fixture(scope="module")
def cff() -> dict:
    return yaml.safe_load(CFF.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bibtex() -> dict[str, str]:
    kind, _key, fields = _parse_bibtex(_bibtex_block(READMES[0]))
    assert kind == "misc"
    return fields


def test_readme_halves_carry_the_same_bibtex():
    english, chinese = (_bibtex_block(path) for path in READMES)
    assert english == chinese


def test_cff_is_a_cff_1_2_0_file(cff):
    assert cff["cff-version"] == "1.2.0"
    for key in ("message", "title", "authors", "preferred-citation"):
        assert cff.get(key), f"CITATION.cff lacks {key}"
    # Not a release pin: the file's own header says so, and this holds it.
    assert "version" not in cff
    assert "date-released" not in cff


def test_preferred_citation_is_the_readme_paper(cff, bibtex):
    paper = cff["preferred-citation"]
    eprint = bibtex["eprint"]
    assert bibtex["archivePrefix"] == "arXiv"
    assert paper["type"] == "generic"
    assert paper["title"] == bibtex["title"]
    assert [_render(a) for a in paper["authors"]] == bibtex["author"].split(" and ")
    assert paper["year"] == int(bibtex["year"])
    assert paper["url"] == bibtex["url"] == f"https://arxiv.org/abs/{eprint}"
    assert paper["doi"] == f"10.48550/arXiv.{eprint}"
    assert f"arXiv:{eprint}" in [i["value"] for i in paper["identifiers"]]
    assert bibtex["primaryClass"] in " ".join(
        i.get("description", "") for i in paper["identifiers"]
    )


def test_cff_renders_the_way_github_reads_it(cff):
    paper = cff["preferred-citation"]
    assert "repository-code" not in paper
    assert {"name": "OpenAI4S Community"} in paper["authors"]
    for author in paper["authors"]:
        assert ("name" in author) != ("given-names" in author), author
    assert cff["repository-code"] == "https://github.com/PKU-YuanGroup/OpenAI4S"


def test_software_authors_match_the_paper(cff):
    assert cff["authors"] == cff["preferred-citation"]["authors"]
