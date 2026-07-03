"""Smoke-load tests for benchmark data corpora (T2.3).

Tests:
  1. test_manifest_determinism — re-run manifest script -> byte-identical output.
  2. test_pyreadstat_load — every XPT in manifest loads via pyreadstat.read_xport().
  3. test_provenance_completeness — PROVENANCE.md has one section per corpus directory.
  4. test_no_sponsor_data_markers — scan XPT metadata + PROVENANCE.md for sponsor keywords.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pyreadstat
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANIFEST_PATH = DATA_DIR / "MANIFEST.sha256"
PROVENANCE_PATH = DATA_DIR / "PROVENANCE.md"

SPONSOR_DENYLIST = [
    "sponsor_internal",
    "confidential",
    "do not redistribute",
]

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_manifest(path: Path) -> list[tuple[str, str]]:
    """Return list of (sha256, relpath) from manifest file."""
    entries: list[tuple[str, str]] = []
    with open(path, encoding="ascii") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            digest, _, relpath = line.partition("  ")
            entries.append((digest, relpath))
    return entries


def _xpt_files_in_manifest() -> list[Path]:
    """Return absolute Paths of all .xpt files listed in the manifest."""
    entries = _parse_manifest(MANIFEST_PATH)
    return [DATA_DIR / relpath for _, relpath in entries if relpath.endswith(".xpt")]


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestManifestDeterminism:
    """T2.3 test 1: re-running the manifest script produces byte-identical output."""

    def test_manifest_determinism(self, tmp_path: Path) -> None:
        original = MANIFEST_PATH.read_bytes()
        rerun_out = tmp_path / "MANIFEST.sha256"
        subprocess.run(
            [sys.executable, "-m", "scripts.build_data_manifest",
             "--data-dir", str(DATA_DIR), "--out", str(rerun_out)],
            check=True,
            cwd=str(ROOT),
        )
        rerun = rerun_out.read_bytes()
        assert rerun == original, (
            "Manifest is NOT deterministic across reruns.\n"
            f"Original {len(original)} bytes vs rerun {len(rerun)} bytes."
        )


class TestPyreadstatLoad:
    """T2.3 test 2: every XPT in manifest loads with >= 1 row and >= 1 column."""

    @pytest.fixture(scope="class")
    def xpt_paths(self) -> list[Path]:
        paths = _xpt_files_in_manifest()
        assert len(paths) >= 1, "No .xpt files found in manifest"
        return paths

    def test_pyreadstat_load(self, xpt_paths: list[Path]) -> None:
        failures: list[str] = []
        for path in xpt_paths:
            relpath = path.relative_to(DATA_DIR).as_posix()
            try:
                df, meta = pyreadstat.read_xport(str(path), encoding="latin1")
            except Exception:
                try:
                    df, meta = pyreadstat.read_xport(str(path))
                except Exception as exc:
                    failures.append(f"{relpath}: {exc}")
                    continue
            if len(df) < 1:
                failures.append(f"{relpath}: 0 rows")
            if len(meta.column_names) < 1:
                failures.append(f"{relpath}: 0 columns")
        assert not failures, (
            f"{len(failures)} XPT(s) failed pyreadstat load:\n"
            + "\n".join(failures)
        )


class TestProvenanceCompleteness:
    """T2.3 test 3: PROVENANCE.md has one section per corpus directory with URL + date."""

    @pytest.fixture(scope="class")
    def provenance_text(self) -> str:
        assert PROVENANCE_PATH.exists(), "PROVENANCE.md not found"
        return PROVENANCE_PATH.read_text(encoding="utf-8")

    def test_provenance_completeness(self, provenance_text: str) -> None:
        # Find top-level corpus directories (those containing data files)
        corpus_dirs: set[str] = set()
        for _, relpath in _parse_manifest(MANIFEST_PATH):
            top = relpath.split("/")[0]
            corpus_dirs.add(top)

        failures: list[str] = []
        for corpus in sorted(corpus_dirs):
            # Check section header exists (## corpus_name)
            if f"## {corpus}" not in provenance_text:
                failures.append(f"Missing section header '## {corpus}'")

            # Build the text block for this section
            section_start = provenance_text.find(f"## {corpus}")
            if section_start == -1:
                continue
            next_section = provenance_text.find("\n## ", section_start + 1)
            section_text = provenance_text[section_start:next_section] if next_section != -1 else provenance_text[section_start:]

            # Check for source URL
            if not re.search(r"https?://", section_text):
                failures.append(f"{corpus}: missing source URL")

            # Check for retrieval date
            if not re.search(r"retrieval date|Retrieval date|202[0-9]-\d{2}-\d{2}", section_text):
                failures.append(f"{corpus}: missing retrieval date")

            # Check for package version (pharmaversesdtm corpora only)
            if "pharmaversesdtm" in corpus:
                if "pharmaversesdtm" not in section_text:
                    failures.append(f"{corpus}: missing package version reference")

        assert not failures, (
            f"Provenance incomplete for {len(failures)} check(s):\n"
            + "\n".join(failures)
        )


class TestNoSponsorDataMarkers:
    """T2.3 test 4: scan XPT metadata and PROVENANCE.md for sponsor-name denylist."""

    def test_no_sponsor_data_markers(self) -> None:
        hits: list[str] = []

        # Scan PROVENANCE.md
        if PROVENANCE_PATH.exists():
            prov_text = PROVENANCE_PATH.read_text(encoding="utf-8").lower()
            for kw in SPONSOR_DENYLIST:
                if kw.lower() in prov_text:
                    hits.append(f"PROVENANCE.md contains denylist keyword: '{kw}'")

        # Scan XPT metadata (study name, first 3 chars of subject IDs)
        for path in _xpt_files_in_manifest():
            relpath = path.relative_to(DATA_DIR).as_posix()
            try:
                df, meta = pyreadstat.read_xport(str(path), encoding="latin1")
            except Exception:
                try:
                    df, meta = pyreadstat.read_xport(str(path))
                except Exception:
                    continue

            # Check study name / label in metadata strings
            meta_str = str(meta).lower()
            for kw in SPONSOR_DENYLIST:
                if kw.lower() in meta_str:
                    hits.append(f"{relpath} metadata contains denylist keyword: '{kw}'")

            # Check first 3 chars of USUBJID values (if column exists)
            if "USUBJID" in df.columns:
                sample_ids = df["USUBJID"].dropna().head(10).astype(str)
                for sid in sample_ids:
                    prefix = str(sid)[:3].lower()
                    for kw in SPONSOR_DENYLIST:
                        if kw.lower() in prefix:
                            hits.append(
                                f"{relpath} USUBJID prefix '{prefix}' matches denylist: '{kw}'"
                            )

        assert not hits, (
            f"Sponsor-name denylist hit {len(hits)}:\n" + "\n".join(hits)
        )
