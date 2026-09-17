"""Cross-check release documents and desktop payloads against the actual bytes.

A checksum manifest can be refreshed after replacing one draft asset. That
does not make its old build receipt, provenance, or sealed evidence describe
the replacement. Both staging and finalization use this read-only boundary;
it never repairs or regenerates evidence for the caller.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

from openai4s.evidence import EvidenceError, verify_package
from scripts.release_gates import GateManifestError, verify_receipt_document
from scripts.release_receipts import ReceiptError, verify_build_receipts

SBOM = "sbom.cdx.json"
PROVENANCE = "provenance.intoto.json"


def _digest(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _document(payload: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(payload)
    except (ValueError, UnicodeError) as error:
        raise ReceiptError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ReceiptError(f"{label} must be a JSON object")
    return document


def _match(actual: Any, expected: Mapping[str, str], label: str) -> None:
    if not isinstance(actual, dict):
        raise ReceiptError(f"{label} has no artifact digest map")
    missing = sorted(set(expected) - actual.keys())
    extra = sorted(actual.keys() - set(expected))
    changed = sorted(
        name
        for name in expected.keys() & actual.keys()
        if actual[name] != expected[name]
    )
    if missing or extra or changed:
        raise ReceiptError(
            f"{label} disagrees with the release assets: missing {missing}, "
            f"unexpected {extra}, changed {changed}; restore the verified assets "
            "or supply evidence from their actual trusted build"
        )


def _rows(rows: Any, *, label: str, sbom: bool = False) -> dict[str, str]:
    if not isinstance(rows, list):
        raise ReceiptError(f"{label} has no distribution list")
    digests: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ReceiptError(f"{label} has a malformed distribution row")
        if sbom and row.get("type") != "distribution":
            continue
        name = row.get("url" if sbom else "name")
        if not isinstance(name, str) or not name or name in digests:
            raise ReceiptError(f"{label} has a missing or duplicate distribution name")
        if sbom:
            hashes = row.get("hashes")
            if not isinstance(hashes, list):
                raise ReceiptError(f"{label} has no hashes for {name}")
            values = [
                item.get("content")
                for item in hashes
                if isinstance(item, dict) and item.get("alg") == "SHA-256"
            ]
            digest = values[0] if len(values) == 1 else None
        else:
            hashes = row.get("digest")
            digest = hashes.get("sha256") if isinstance(hashes, dict) else None
        if not isinstance(digest, str):
            raise ReceiptError(f"{label} has no unique SHA-256 for {name}")
        digests[name] = digest
    return digests


def _windows_payloads(
    files: Mapping[str, Path], digests: Mapping[str, str], version: str
) -> None:
    for name, path in files.items():
        match = re.fullmatch(
            rf"OpenAI4S-{re.escape(version)}-windows-(x86_64|arm64)\.zip", name
        )
        if match is None:
            continue
        arch = "aarch64" if match[1] == "arm64" else "x86_64"
        linux = f"OpenAI4S-{version}-linux-{arch}.tar.gz"
        if linux not in files:
            raise ReceiptError(f"{name} payload has no matching release asset {linux}")
        expected_member = f"{path.stem}/payload/{linux}"
        with zipfile.ZipFile(path) as archive:
            members = [
                info for info in archive.infolist() if info.filename.endswith(".tar.gz")
            ]
            if len(members) != 1 or members[0].filename != expected_member:
                raise ReceiptError(f"{name} must contain exactly the payload {linux}")
            member = members[0]
            # Check before streaming: a forged zip cannot make verification
            # decompress more payload bytes than the independently held asset.
            if member.file_size != files[linux].stat().st_size:
                raise ReceiptError(f"{name} payload size differs from {linux}")
            with archive.open(member) as stream:
                actual = _digest(stream)
            if actual != digests[linux]:
                raise ReceiptError(
                    f"{name} payload does not match release asset {linux}"
                )


def verify_release_consistency(
    assets: Sequence[Path], *, version: str, required_kinds: Sequence[str]
) -> None:
    """Require the complete staged evidence chain, including manual recovery.

    The evidence is a pre-upload snapshot: its report covers distributions,
    SBOM and provenance, but cannot contain its own hash or SHA256SUMS. Build
    receipts are carried inside that archive, not as public sidecars.
    """
    try:
        _verify(assets, version=version, required_kinds=required_kinds)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        zipfile.BadZipFile,
        EvidenceError,
        RuntimeError,
        GateManifestError,
    ) as error:
        raise ReceiptError(
            f"release consistency verification failed: {error}"
        ) from error


def _verify(
    assets: Sequence[Path], *, version: str, required_kinds: Sequence[str]
) -> None:
    files = {path.name: path for path in assets if path.name != "SHA256SUMS"}
    evidence_name = f"openai4s-{version}-evidence.zip"
    required = {SBOM, PROVENANCE, evidence_name}
    if not required <= files.keys():
        raise ReceiptError(
            f"release is missing evidence assets: {sorted(required - files.keys())}"
        )
    digests = {}
    for name, path in files.items():
        with path.open("rb") as stream:
            digests[name] = _digest(stream)
    distributions = {
        name: digest for name, digest in digests.items() if name not in required
    }
    if not distributions:
        raise ReceiptError("release evidence names no distributions")

    provenance = _document(files[PROVENANCE].read_bytes(), PROVENANCE)
    definition = provenance["predicate"]["buildDefinition"]
    if definition["externalParameters"]["version"] != version:
        raise ReceiptError("provenance names another release version")
    _match(
        _rows(provenance.get("subject"), label=PROVENANCE), distributions, PROVENANCE
    )
    sbom = _document(files[SBOM].read_bytes(), SBOM)
    if sbom["metadata"]["component"]["version"] != version:
        raise ReceiptError("SBOM names another release version")
    _match(
        _rows(sbom.get("externalReferences"), label=SBOM, sbom=True),
        distributions,
        SBOM,
    )

    verdict = verify_package(files[evidence_name])
    if not verdict.get("ok") or verdict.get("format") != "openai4s-release-evidence":
        raise ReceiptError(
            f"{evidence_name} failed verification: {verdict.get('problems')}"
        )
    with zipfile.ZipFile(files[evidence_name]) as archive:
        report = _document(archive.read("release-report.json"), "release-report.json")
        if report.get("version") != version:
            raise ReceiptError("sealed release report names another version")
        source_sha = report.get("source_sha")
        if not isinstance(source_sha, str) or not re.fullmatch(
            r"[0-9a-f]{40}", source_sha
        ):
            raise ReceiptError("sealed release report has no frozen source SHA")
        sources = definition["resolvedDependencies"]
        if (
            not isinstance(sources, list)
            or len(sources) != 1
            or sources[0]["digest"].get("sha1") != source_sha
        ):
            raise ReceiptError(
                "provenance source SHA differs from the sealed release report"
            )
        quality = _document(
            archive.read("artifacts/quality-receipt.json"), "sealed quality receipt"
        )
        verify_receipt_document(quality, expected_sha=source_sha)
        _match(
            report.get("artifacts"),
            {name: value for name, value in digests.items() if name != evidence_name},
            "sealed release report",
        )
        for name in (SBOM, PROVENANCE):
            if (
                hashlib.sha256(archive.read(f"artifacts/{name}")).hexdigest()
                != digests[name]
            ):
                raise ReceiptError(f"sealed {name} differs from the published asset")
        with tempfile.TemporaryDirectory(
            prefix="openai4s-evidence-receipts-"
        ) as scratch:
            receipts = []
            coverage: dict[str, str] = {}
            for member in archive.namelist():
                if not re.fullmatch(r"artifacts/build-receipt-[a-z]+\.json", member):
                    continue
                payload = archive.read(member)
                document = _document(payload, member)
                rows = document.get("artifacts")
                if not isinstance(rows, list):
                    raise ReceiptError(f"{member} lists no artifacts")
                for row in rows:
                    if not isinstance(row, dict):
                        raise ReceiptError(f"{member} has a malformed artifact row")
                    name = row.get("name")
                    if (
                        not isinstance(name, str)
                        or name not in distributions
                        or name in coverage
                    ):
                        raise ReceiptError(
                            f"{member} has an unexpected or duplicate artifact {name!r}"
                        )
                    coverage[name] = row.get("sha256")
                receipt = Path(scratch) / Path(member).name
                receipt.write_bytes(payload)
                receipts.append(receipt)
            _match(coverage, distributions, "sealed build receipts")
            # All supplied paths are in the staging/download directory. No
            # archive member is extracted and every receipt row was allowlisted
            # against real distribution names before the existing verifier reads.
            verify_build_receipts(
                receipts,
                expected_sha=source_sha,
                assets_dir=files[SBOM].parent,
                required_kinds=required_kinds,
            )
    _windows_payloads(files, digests, version)
