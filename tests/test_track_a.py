"""Tests for Track A regression analysis (T6.3).

Covers: B2 CORE parser loads flags, oncology filter, flag count, Jaccard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.baselines.b2_core import _parse_flags, run
from eval.flag_schema import FlagSet

PILOT1 = Path("data/pilot1")
CORE_CACHE = Path("eval/core_pilot1_raw.json")


def _synthetic_core_raw() -> dict:
    """Minimal CORE JSON with oncology and non-oncology rows."""
    return {
        "Issue_Details": [
            {
                "core_id": "CORE-000047",
                "message": "DM issue",
                "executability": "yes",
                "dataset": "dm.xpt",
                "USUBJID": "01-701-1015",
                "row": 1,
                "SEQ": "",
                "variables": ["USUBJID"],
                "values": ["01-701-1015"],
            },
            {
                "core_id": "CORE-000108",
                "message": "EX issue",
                "executability": "yes",
                "dataset": "ex.xpt",
                "USUBJID": "01-701-1015",
                "row": 1,
                "SEQ": "1",
                "variables": ["USUBJID"],
                "values": ["01-701-1015"],
            },
            {
                "core_id": "CORE-000019",
                "message": "TS issue (non-oncology)",
                "executability": "yes",
                "dataset": "ts.xpt",
                "USUBJID": "",
                "row": 1,
                "SEQ": "",
                "variables": [],
                "values": [],
            },
        ]
    }


# ---------------------------------------------------------------------------
# 1. B2 CORE parser loads flags
# ---------------------------------------------------------------------------

class TestB2CoreParser:
    def test_parser_loads_flags(self):
        """B2 parser reads cached JSON and produces FlagRecords."""
        raw = _synthetic_core_raw()
        flags = _parse_flags(raw)
        assert len(flags) == 2
        assert all(f.source == "B2_CORE" for f in flags)
        assert flags[0].subject == "01-701-1015"
        assert flags[0].rule_id == "CORE-000047"

    def test_oncology_filter(self):
        """Only DM/EX/TU/TR/RS issues retained; TS excluded."""
        raw = _synthetic_core_raw()
        flags = _parse_flags(raw)
        domains = {f.domain for f in flags}
        assert domains == {"DM", "EX"}
        # Verify ts.xpt was filtered out
        assert len(flags) == 2

    @pytest.mark.skipif(not CORE_CACHE.exists(), reason="core_pilot1_raw.json not found")
    def test_flag_count_matches_expected(self):
        """Oncology flag count matches expected (941)."""
        raw = json.loads(CORE_CACHE.read_text(encoding="utf-8"))
        flags = _parse_flags(raw)
        assert len(flags) == 941


# ---------------------------------------------------------------------------
# 2. Track A Jaccard computation
# ---------------------------------------------------------------------------

class TestTrackAJaccard:
    @pytest.mark.skipif(
        not (PILOT1.exists() and CORE_CACHE.exists()),
        reason="pilot1 data or CORE cache not available",
    )
    def test_jaccard_computed(self):
        """Run Track A analysis, Jaccard is a float in [0, 1]."""
        from scripts.track_a_analysis import run_analysis
        results = run_analysis(PILOT1)
        assert "jaccard" in results
        j = results["jaccard"]
        assert isinstance(j, float)
        assert 0.0 <= j <= 1.0

    @pytest.mark.skipif(not CORE_CACHE.exists(), reason="core_pilot1_raw.json not found")
    def test_run_on_pilot1_dir(self):
        """run() finds cache when called with pilot1 data dir."""
        flagset = run(PILOT1)
        assert isinstance(flagset, FlagSet)
        assert len(flagset) == 941
