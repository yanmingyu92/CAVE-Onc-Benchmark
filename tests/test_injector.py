"""Tests for bench/injector.py and bench/mutations.py (T5.6)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bench.injector import Injector
from bench.mutations import MUTATIONS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def injector(tmp_path):
    """Provide an Injector with real data sources and temp output."""
    return Injector(
        source_dirs=["data/pilot1", "data/pharmaversesdtm_recist"],
        output_dir=tmp_path / "output",
    )


@pytest.fixture()
def frames():
    """Pre-loaded frames dict for direct mutation tests."""
    inj = Injector(
        source_dirs=["data/pilot1", "data/pharmaversesdtm_recist"],
    )
    return inj._load_all()


# ---------------------------------------------------------------------------
# 1. A01 — SLD decrease ≥30% with RSORRES=PD
# ---------------------------------------------------------------------------

def test_a01_sld_vs_pd(frames):
    """A01: RSORRES changed to PD at visit with ≥30% SLD decrease."""
    mutator = MUTATIONS["A01"]
    result, meta = mutator({k: v.copy() for k, v in frames.items()})
    assert meta["archetype"] == "A01"
    assert meta["usubjid"] != ""
    rs = result["RS"]
    subj = meta["usubjid"]
    # At least one row for this subject should have RSORRES=PD
    pd_rows = rs[(rs["USUBJID"] == subj) & (rs["RSORRES"] == "PD")]
    assert len(pd_rows) >= 1


# ---------------------------------------------------------------------------
# 2. A02 — New lesion without RS escalation
# ---------------------------------------------------------------------------

def test_a02_new_lesion(frames):
    """A02: New TU record added, RSORRES stays SD."""
    mutator = MUTATIONS["A02"]
    orig_tu_count = len(frames["TU"])
    result, meta = mutator({k: v.copy() for k, v in frames.items()})
    assert meta["archetype"] == "A02"
    assert len(result["TU"]) == orig_tu_count + 1
    # RS unchanged
    assert result["RS"].equals(frames["RS"])


# ---------------------------------------------------------------------------
# 3. A05 — Conflicting demographics DM vs SUPPDM
# ---------------------------------------------------------------------------

def test_a05_conflicting_demographics(frames):
    """A05: SUPPDM QNAM=SEX record conflicts with DM.SEX."""
    mutator = MUTATIONS["A05"]
    result, meta = mutator({k: v.copy() for k, v in frames.items()})
    assert meta["archetype"] == "A05"
    subj = meta["usubjid"]
    dm_sex = str(result["DM"][result["DM"]["USUBJID"] == subj]["SEX"].iloc[0])
    supp = result["SUPPDM"]
    conflict_rows = supp[(supp["USUBJID"] == subj) & (supp["QNAM"] == "SEX")]
    assert len(conflict_rows) >= 1
    assert conflict_rows["QVAL"].iloc[0] != dm_sex


# ---------------------------------------------------------------------------
# 4. A07 — Confirmed PR without confirmation visit
# ---------------------------------------------------------------------------

def test_a07_pr_no_confirmation(frames):
    """A07: Post-PR confirmation visits removed from RS."""
    mutator = MUTATIONS["A07"]
    result, meta = mutator({k: v.copy() for k, v in frames.items()})
    assert meta["archetype"] == "A07"
    subj = meta["usubjid"]
    rs = result["RS"]
    # Must have at least one PR row
    pr_rows = rs[(rs["USUBJID"] == subj) & (rs["RSORRES"] == "PR")]
    assert len(pr_rows) >= 1


# ---------------------------------------------------------------------------
# 5. RELREC preservation
# ---------------------------------------------------------------------------

def test_relrec_preserved_after_mutations(frames, injector):
    """After injecting A09 (remove DS) and A14 (remove EX), RELREC has no orphans."""
    inj = injector
    # Test A09 (removes DS records → RELREC cleaned)
    frames_a09 = {k: v.copy() for k, v in frames.items()}
    from bench.mutations import mutate_A09
    result, _ = mutate_A09(frames_a09)
    assert inj.verify_relrec(result)

    # Test A14 (removes EX records → RELREC cleaned)
    frames_a14 = {k: v.copy() for k, v in frames.items()}
    from bench.mutations import mutate_A14
    result, _ = mutate_A14(frames_a14)
    assert inj.verify_relrec(result)


# ---------------------------------------------------------------------------
# 6. Manifest output
# ---------------------------------------------------------------------------

def test_manifest_output(injector):
    """Inject A01 and verify manifest structure."""
    meta = injector.inject("A01")
    manifest = injector.manifest()
    assert len(manifest) == 1
    assert manifest[0]["archetype"] == "A01"
    assert "usubjid" in manifest[0]
    assert "description" in manifest[0]
    assert "domains_modified" in manifest[0]
    # Write manifest and verify it's valid JSON
    path = injector.write_manifest()
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1


# ---------------------------------------------------------------------------
# 7. Full inject pipeline writes files
# ---------------------------------------------------------------------------

def test_inject_writes_files(injector):
    """Inject A12 and verify output XPT files are created."""
    injector.inject("A12")
    out_dir = injector.output_dir / "A12"
    assert out_dir.exists()
    # At least dm.xpt should exist
    files = list(out_dir.glob("*.xpt")) + list(out_dir.glob("*.csv"))
    assert len(files) >= 1


# ---------------------------------------------------------------------------
# 8. All 20 mutations are callable
# ---------------------------------------------------------------------------

def test_all_mutations_registered():
    """MUTATIONS dict has exactly 20 entries (A01–A20)."""
    assert len(MUTATIONS) == 20
    for i in range(1, 21):
        assert f"A{i:02d}" in MUTATIONS
