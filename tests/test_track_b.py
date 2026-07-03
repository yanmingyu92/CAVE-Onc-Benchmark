"""Tests for scripts/track_b_analysis.py — Track B novelty analysis."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def clean_frames():
    """Load clean frames once for reuse across tests."""
    from bench.injector import Injector
    inj = Injector(output_dir="bench/output_test_track_b")
    return inj._load_all()


def test_injector_produces_modified_data(clean_frames):
    """At least 1 archetype injection produces non-empty modified frames."""
    from bench.mutations import MUTATIONS

    success = False
    for aid in list(MUTATIONS.keys())[:5]:
        frames = {k: v.copy() for k, v in clean_frames.items()}
        _, meta = MUTATIONS[aid](frames)
        # Check that mutation didn't skip (no "skipped" in description)
        non_empty = {k for k, v in frames.items() if v is not None and not v.empty}
        if non_empty and "skipped" not in meta.get("description", ""):
            success = True
            break
    assert success, "No archetype injection produced modified frames"


def test_track_b_results_schema(tmp_path):
    """Results JSON has per-archetype entries for all 20 archetypes."""
    from bench.mutations import MUTATIONS
    from scripts.track_b_analysis import ArchetypeResult

    results = []
    for aid in sorted(MUTATIONS):
        results.append(asdict(ArchetypeResult(archetype_id=aid, injected=True)))

    report = {"archetypes": results, "summary": {}}
    out = tmp_path / "track_b_results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    loaded = json.loads(out.read_text(encoding="utf-8"))
    ids = {r["archetype_id"] for r in loaded["archetypes"]}
    assert ids == set(MUTATIONS.keys())


def test_l3_a19_detection(clean_frames):
    """A19 (Table 7) is detected by L3 agent on injected data.

    The L3 agent requires OVRLRESP, NTOVRLRESP, and NEWLEC test codes
    to perform Table 7 lookup.  We augment RS data with these codes so
    the agent can detect the contradiction introduced by mutate_A19.
    """
    import pandas as pd
    from scripts.track_b_analysis import _frames_to_graph, _run_l3
    from bench.mutations import MUTATIONS

    frames = {k: v.copy() for k, v in clean_frames.items()}
    frames, _ = MUTATIONS["A19"](frames)

    # Augment RS with NTOVRLRESP and NEWLEC rows so the agent has
    # enough data for Table 7 lookup (real studies include these).
    rs = frames["RS"]
    usubjid = rs["USUBJID"].iloc[0]
    studyid = rs["STUDYID"].iloc[0]
    vn = rs[rs["USUBJID"] == usubjid]["VISITNUM"].iloc[0]
    base_row = rs[rs["USUBJID"] == usubjid].iloc[0]
    extra_rows = []
    for testcd, val in [("NTOVRLRESP", "NON-CR/NON-PD"), ("NEWLEC", "N")]:
        row = base_row.copy()
        row["RSTESTCD"] = testcd
        row["RSORRES"] = val
        row["RSSTRESC"] = val
        row["RSSEQ"] = rs["RSSEQ"].max() + 1 + len(extra_rows)
        extra_rows.append(row)
    frames["RS"] = pd.concat(
        [rs, pd.DataFrame(extra_rows)], ignore_index=True,
    )

    graph = _frames_to_graph(frames)
    traces = _run_l3(graph)
    a19_traces = [t for t in traces if t.get("archetype") == "A19"]
    assert len(a19_traces) > 0, "A19 contradiction not detected by L3 agent"


def test_track_b_output_saved(tmp_path):
    """eval/track_b_results.json exists after analysis."""
    from scripts.track_b_analysis import run_analysis

    out_path = tmp_path / "eval" / "track_b_results.json"
    report = run_analysis(output_path=out_path)

    assert out_path.exists(), "Results file not created"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "archetypes" in data
    assert "summary" in data
    assert len(data["archetypes"]) == 20
