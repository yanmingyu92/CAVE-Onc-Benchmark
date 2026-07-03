"""Guards for the empirical Pinnacle 21 FDA-engine Track B baseline (Gate 1).

The decisive result: the branded FDA production engine detects 0/10 of the non-CORE
cross-domain RECIST contradictions (same as the open CORE engine), while CAVE detects
10/10. These tests lock the invariant and the adjudication accounting so a stale or
mis-scored regeneration is caught.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "eval" / "p21_fda_benchmark.json"


@pytest.fixture(scope="module")
def bench() -> dict:
    if not BENCH.is_file():
        pytest.skip("p21_fda_benchmark.json absent — run scripts.run_p21_fda_baseline")
    return json.loads(BENCH.read_text(encoding="utf-8"))


def test_noncore_class_is_zero(bench):
    """The expressiveness claim: P21 FDA detects none of the non-CORE cross-domain class."""
    assert bench["HEADLINE"]["noncore_crossdomain_detected"] == "0/10"


def test_direct_count_matches_per_archetype(bench):
    """HEADLINE direct count must equal the per-archetype adjudication (no drift)."""
    direct = sum(1 for r in bench["per_archetype"] if r.get("p21_detects_contradiction"))
    assert bench["HEADLINE"]["p21_detects_DIRECT"] == f"{direct}/20"
    # All direct detections must fall in the CORE-seeded structural class.
    for r in bench["per_archetype"]:
        if r.get("p21_detects_contradiction"):
            assert r["category"] == "core_derived_structural", r["archetype"]


def test_direct_rule_is_in_new_ids(bench):
    """A 'direct' detection must cite a rule P21 actually fired on the injected corpus."""
    for r in bench["per_archetype"]:
        if r.get("p21_detects_contradiction"):
            assert r["matched_p21_rule"] in r["new_p21_rule_ids"], r["archetype"]


def test_run_stub_and_loader():
    from eval.baselines import b1_p21
    with pytest.raises(NotImplementedError):
        b1_p21.run(ROOT)
    assert b1_p21.fda_result()["HEADLINE"]["noncore_crossdomain_detected"] == "0/10"
