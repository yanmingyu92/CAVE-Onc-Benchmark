"""Tests for scripts/p8_benchmark.py — P8 extended benchmark."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def clean_frames():
    """Load clean frames once for reuse across tests."""
    from bench.injector import Injector
    inj = Injector(output_dir="bench/output_test_p8")
    return inj._load_all()


def test_enriched_rs_has_required_codes(clean_frames):
    """Verify RS augmentation adds NTOVRLRESP + NEWLEC rows."""
    import pandas as pd
    from scripts.p8_benchmark import enrich_rs

    frames = {k: v.copy() for k, v in clean_frames.items()}
    rs_before = frames["RS"]
    testcds_before = set(rs_before["RSTESTCD"].unique())

    frames = enrich_rs(frames)
    rs_after = frames["RS"]
    testcds_after = set(rs_after["RSTESTCD"].unique())

    assert "NTOVRLRESP" in testcds_after, "NTOVRLRESP missing after enrichment"
    assert "NEWLEC" in testcds_after, "NEWLEC missing after enrichment"
    assert len(rs_after) > len(rs_before), "RS row count did not increase"
    # Each USUBJID gets 2 extra rows
    n_subjects = rs_before["USUBJID"].nunique()
    assert len(rs_after) == len(rs_before) + 2 * n_subjects


def test_a19_detected_with_enriched_rs(clean_frames):
    """A19 is detected by L3 on enriched + injected data."""
    from scripts.p8_benchmark import enrich_rs, _run_archetype
    from scripts.track_b_analysis import _run_l1

    # Get clean baseline with enrichment for fair delta
    enriched_clean = enrich_rs({k: v.copy() for k, v in clean_frames.items()})
    from scripts.track_b_analysis import _frames_to_graph
    clean_l1 = _run_l1(_frames_to_graph(enriched_clean))

    result = _run_archetype("A19", clean_frames, clean_l1)
    assert result.l3_detected, (
        f"A19 not detected by L3 on enriched data (traces={result.l3_traces})"
    )


def test_benchmark_results_schema(tmp_path):
    """p8_benchmark_results.json has required keys and all 20 archetypes."""
    from bench.mutations import MUTATIONS
    from scripts.p8_benchmark import run_benchmark

    out_path = tmp_path / "eval" / "p8_benchmark_results.json"
    report = run_benchmark(output_path=out_path)

    # Top-level keys
    for key in ("track_a", "track_b_enriched", "ablation", "timing"):
        assert key in report, f"Missing top-level key: {key}"

    # All 20 archetypes present
    ids = {a["archetype_id"] for a in report["track_b_enriched"]["archetypes"]}
    assert ids == set(MUTATIONS.keys()), f"Missing archetypes: {set(MUTATIONS.keys()) - ids}"

    # Required fields per archetype
    required_fields = {
        "archetype_id", "l1_detected", "l3_detected", "cave_detected",
        "l1_flag_delta", "l3_traces", "detection_source",
        "l1_time_s", "l3_time_s",
    }
    for a in report["track_b_enriched"]["archetypes"]:
        missing = required_fields - set(a.keys())
        assert not missing, f"{a['archetype_id']} missing fields: {missing}"

    # Summary keys
    summary = report["track_b_enriched"]["summary"]
    for key in ("l1_detection_rate", "l3_detection_rate", "cave_detection_rate"):
        assert key in summary, f"Missing summary key: {key}"

    # Timing keys
    timing = report["timing"]
    for key in ("mean_per_archetype_l1_s", "mean_per_archetype_l3_s",
                "mean_full_pipeline_s", "cave_to_baseline_ratio"):
        assert key in timing, f"Missing timing key: {key}"

    # File was written
    assert out_path.exists(), "Results file not created"
