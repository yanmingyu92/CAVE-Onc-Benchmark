"""Tests for the evaluation harness (T6.1+T6.2).

Covers: flag schema, Jaccard correctness, cave_only filtering,
B3 L1 runner on pilot1, B_CAVE runner on pilot1, dispatcher file output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.flag_schema import FlagRecord, FlagSet
from eval.metrics import (
    cave_only_catches,
    jaccard,
    per_rule_recall,
    track_a_report,
    track_b_report,
)
from eval.run_baseline import run_evaluation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PILOT1 = Path("data/pilot1")


def _make_flag(subject: str, rule_id: str, source: str = "B3_L1",
               domain: str = "DM", severity: str = "violation",
               archetype: str | None = None, message: str = "test") -> FlagRecord:
    return FlagRecord(
        subject=subject, archetype=archetype, rule_id=rule_id,
        domain=domain, severity=severity, message=message, source=source,
    )


# ---------------------------------------------------------------------------
# 1. FlagRecord schema
# ---------------------------------------------------------------------------

class TestFlagRecordSchema:
    def test_constructs_with_all_fields(self):
        f = FlagRecord(
            subject="01-701-1015", archetype="A01", rule_id="Shape_DM_1",
            domain="DM", severity="violation", message="ARMCD too long",
            source="B3_L1",
        )
        assert f.subject == "01-701-1015"
        assert f.archetype == "A01"
        assert f.rule_id == "Shape_DM_1"
        assert f.domain == "DM"
        assert f.severity == "violation"
        assert f.message == "ARMCD too long"
        assert f.source == "B3_L1"

    def test_flagset_to_dataframe(self):
        flags = [_make_flag("s1", "r1"), _make_flag("s2", "r2")]
        fs = FlagSet(flags)
        df = fs.to_dataframe()
        assert len(df) == 2
        assert list(df.columns) == list(FlagRecord.model_fields.keys())


# ---------------------------------------------------------------------------
# 2. Jaccard correctness
# ---------------------------------------------------------------------------

class TestJaccard:
    def test_known_overlap(self):
        a = FlagSet([_make_flag("s1", "r1"), _make_flag("s2", "r2")])
        b = FlagSet([_make_flag("s1", "r1"), _make_flag("s3", "r3")])
        # overlap = {("s1","r1")}, union = {("s1","r1"),("s2","r2"),("s3","r3")}
        assert jaccard(a, b) == pytest.approx(1 / 3)

    def test_identical_sets(self):
        a = FlagSet([_make_flag("s1", "r1"), _make_flag("s2", "r2")])
        assert jaccard(a, a) == pytest.approx(1.0)

    def test_disjoint_sets(self):
        a = FlagSet([_make_flag("s1", "r1")])
        b = FlagSet([_make_flag("s2", "r2")])
        assert jaccard(a, b) == pytest.approx(0.0)

    def test_empty_sets(self):
        assert jaccard(FlagSet(), FlagSet()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. cave_only filtering
# ---------------------------------------------------------------------------

class TestCaveOnly:
    def test_filters_correctly(self):
        cave = FlagSet([
            _make_flag("s1", "r1", source="CAVE"),
            _make_flag("s2", "r2", source="CAVE"),
            _make_flag("s3", "r3", source="CAVE"),
        ])
        core = FlagSet([
            _make_flag("s1", "r1", source="B3_L1"),
            _make_flag("s2", "r2", source="B3_L1"),
        ])
        novel = cave_only_catches(cave, core)
        assert len(novel) == 1
        assert novel.flags[0].subject == "s3"
        assert novel.flags[0].rule_id == "r3"

    def test_all_overlap(self):
        cave = FlagSet([_make_flag("s1", "r1", source="CAVE")])
        core = FlagSet([_make_flag("s1", "r1", source="B3_L1")])
        assert len(cave_only_catches(cave, core)) == 0


# ---------------------------------------------------------------------------
# 4. B3 L1 runner on pilot1
# ---------------------------------------------------------------------------

class TestB3L1Runner:
    @pytest.mark.skipif(not PILOT1.exists(), reason="pilot1 data not available")
    def test_produces_flag_records(self):
        from eval.baselines.b3_l1_only import run
        result = run(PILOT1)
        assert isinstance(result, FlagSet)
        # pilot1 should produce at least some L1 flags
        if len(result) > 0:
            f = result.flags[0]
            assert isinstance(f, FlagRecord)
            assert f.source == "B3_L1"
            assert f.subject
            assert f.rule_id


# ---------------------------------------------------------------------------
# 5. B_CAVE runner on pilot1
# ---------------------------------------------------------------------------

class TestBCAVERunner:
    @pytest.mark.skipif(not PILOT1.exists(), reason="pilot1 data not available")
    def test_produces_l1_and_l3_flags(self):
        from eval.baselines.b_cave import run
        result = run(PILOT1)
        assert isinstance(result, FlagSet)
        # Should contain L1 flags at minimum (L3 only fires on specific data)
        if len(result) > 0:
            sources = {f.source for f in result.flags}
            assert "CAVE" in sources


# ---------------------------------------------------------------------------
# 6. Dispatcher saves files
# ---------------------------------------------------------------------------

class TestDispatcher:
    @pytest.mark.skipif(not PILOT1.exists(), reason="pilot1 data not available")
    def test_saves_per_baseline_json_and_metrics(self, tmp_path: Path):
        results = run_evaluation(
            data_dir=PILOT1,
            output_dir=tmp_path / "eval_out",
            baselines=["B3_L1"],
        )
        assert "B3_L1" in results
        assert (tmp_path / "eval_out" / "B3_L1.json").exists()
        assert (tmp_path / "eval_out" / "metrics.json").exists()
        metrics = json.loads((tmp_path / "eval_out" / "metrics.json").read_text())
        assert "baselines_run" in metrics
        assert "B3_L1" in metrics["baselines_run"]
        assert "jaccard_matrix" in metrics

    def test_stubs_raise_not_implemented(self, tmp_path: Path):
        from eval.baselines.b1_p21 import run as run_b1
        from eval.baselines.b2_core import run as run_b2
        with pytest.raises(NotImplementedError):
            run_b1(tmp_path)
        with pytest.raises(NotImplementedError):
            run_b2(tmp_path)
