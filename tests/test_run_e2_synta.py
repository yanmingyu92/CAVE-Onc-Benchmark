"""Tests for the E2 mutation-transfer runner (scripts/run_e2_real_data).

The mapped Synta SDTM is gitignored (*.xpt), so the integration tests SKIP when
``data/real_sdtm/synta`` is absent (e.g. CI). The pure classification/structure
tests always run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bench.mutations import MUTATIONS
from scripts import run_e2_real_data as e2

SRC = Path("data/real_sdtm/synta")
_HAS_DATA = (SRC / "rs.xpt").exists()
needs_data = pytest.mark.skipif(not _HAS_DATA, reason="mapped Synta SDTM absent (gitignored)")


# -- classification (always runs) --------------------------------------------

def test_a17_is_the_only_cross_subject():
    assert e2.CROSS_SUBJECT == {"A17"}


def test_a19_is_always_not_applicable():
    assert "A19" in e2.ALWAYS_NA
    assert e2.not_applicable({}) == dict(e2.ALWAYS_NA) or "A19" in e2.not_applicable({})


def test_sparse_trial_marks_ex_and_date_family_na():
    """A trial with no EX, no dates, no ACTARMCD (Synta-like) -> the full N/A set."""
    import pandas as pd
    sparse = {"RS": pd.DataFrame({"RSDTC": [""]}), "DM": pd.DataFrame({"USUBJID": ["x"]})}
    na = e2.not_applicable(sparse)
    for aid in ("A03", "A07", "A09", "A10", "A11", "A14", "A15", "A19", "A20"):
        assert aid in na, f"{aid} should be N/A on a sparse trial"


def test_rich_trial_widens_applicability():
    """A trial WITH EX + ISO dates + ACTARMCD (CA012-like) -> EX/date family applicable."""
    import pandas as pd
    rich = {
        "RS": pd.DataFrame({"RSDTC": ["2010-01-01"]}),
        "DM": pd.DataFrame({"USUBJID": ["x"], "ACTARMCD": ["B"]}),
        "EX": pd.DataFrame({"USUBJID": ["x"], "EXSTDTC": ["2010-01-01"]}),
    }
    na = e2.not_applicable(rich)
    for aid in ("A07", "A09", "A10", "A11", "A14", "A15", "A20"):
        assert aid not in na, f"{aid} should be applicable on a rich trial"
    assert "A19" in na  # L3 always N/A


# -- subgraph restriction (needs data) ---------------------------------------

@pytest.fixture(scope="module")
def frames():
    from bench.injector import Injector
    return Injector(source_dirs=[str(SRC)])._load_all()


@needs_data
def test_subject_frames_restricts_to_one_subject(frames):
    s = sorted(frames["DM"]["USUBJID"].unique())[0]
    mini = e2._subject_frames(frames, s)
    for dom, df in mini.items():
        if df is None or df.empty or "USUBJID" not in df.columns:
            continue
        assert set(df["USUBJID"].unique()) <= {s}, f"{dom} leaked other subjects"
    # trial-design TA (no USUBJID) is kept whole
    assert len(mini["TA"]) == len(frames["TA"])


@needs_data
def test_subgraph_detection_is_per_subject_targeted(frames):
    """A02 (new lesion w/o RS escalation) is detected on a real subject subgraph,
    newly induced by injection (not present on the clean subgraph)."""
    s = sorted(frames["DM"]["USUBJID"].unique())[0]
    fired, new = e2._inject_detect_subgraph(frames, "A02", s, "oxigraph")
    assert fired, f"A02 not detected on {s}; new shapes were {sorted(new)}"


@needs_data
def test_per_subject_archetype_detected_within_candidates(frames):
    """A05 (DM vs SUPPDM sex conflict) transfers to real structure on >=1 candidate."""
    rec = e2.analyze_per_subject("A05", frames, clean_full=set(), backend="oxigraph", k=3)
    assert rec["status"] == "detected"
    assert rec["candidates_detected"] >= 1
