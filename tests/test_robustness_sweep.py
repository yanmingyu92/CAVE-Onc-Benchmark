"""Gate 2b — unit tests for the adversarial robustness-sweep perturbations.

These cover the deterministic, pure-data perturbation helpers (no SHACL run), so
they are fast. The end-to-end sweep on real trials is exercised by running
``scripts/run_robustness_sweep.py`` and is recorded in eval/robustness_sweep.json.
"""
from __future__ import annotations

import random

import pandas as pd

from scripts.run_robustness_sweep import (
    _archetype_flag_count, _drop_fraction, _subset_subjects,
)


def _frames() -> dict[str, pd.DataFrame]:
    dm = pd.DataFrame({"USUBJID": [f"S{i}" for i in range(10)], "ARMCD": ["A"] * 10})
    tr = pd.DataFrame({"USUBJID": [f"S{i%10}" for i in range(100)],
                       "TRTESTCD": ["LDIAM"] * 100, "VISITNUM": [1.0] * 100})
    return {"DM": dm, "TR": tr}


def test_drop_fraction_is_deterministic_and_correct_size():
    frames = _frames()
    a = _drop_fraction(frames, ("TR",), 0.25, random.Random(1))
    b = _drop_fraction(frames, ("TR",), 0.25, random.Random(1))
    assert len(a["TR"]) == 75  # 25% of 100 dropped
    assert a["TR"].equals(b["TR"])  # same seed -> identical result
    # original frames are not mutated
    assert len(frames["TR"]) == 100


def test_drop_fraction_zero_is_noop():
    frames = _frames()
    out = _drop_fraction(frames, ("TR",), 0.0, random.Random(1))
    assert len(out["TR"]) == 100


def test_subset_subjects_caps_and_is_seeded():
    frames = _frames()
    out = _subset_subjects(frames, 4, random.Random(7))
    assert out["DM"]["USUBJID"].nunique() == 4
    # TR rows restricted to the retained subjects only
    assert set(out["TR"]["USUBJID"]).issubset(set(out["DM"]["USUBJID"]))


def test_archetype_flag_count_ignores_non_archetype_labels():
    flags = {("A01", "S1"), ("A03", "S2"), ("S5", "S3"), ("recist", "S4")}
    assert _archetype_flag_count(flags) == 2


def test_compatible_cooccurrence_excludes_mutually_exclusive_rs_mutations():
    """At most one RS-overall-response mutation may co-occur (they clobber each other)."""
    from scripts.run_robustness_sweep import _compatible_cooccurrence_set

    detectable = ["A01", "A06", "A07", "A08", "A10", "A12"]  # A01/A06/A07 clobber
    co, excluded = _compatible_cooccurrence_set(detectable)
    rs_group = {"A01", "A06", "A07"}
    # exactly one RS-response archetype survives in the co-occurring set
    assert len(set(co) & rs_group) == 1
    # the other two are reported as mutually exclusive, not silently dropped
    assert set(excluded) == (rs_group - set(co))
    # non-conflicting archetypes all survive
    assert {"A08", "A10", "A12"}.issubset(set(co))


def test_compatible_cooccurrence_no_conflict_keeps_all():
    from scripts.run_robustness_sweep import _compatible_cooccurrence_set

    detectable = ["A08", "A10", "A11", "A12"]  # disjoint DM fields, no conflict
    co, excluded = _compatible_cooccurrence_set(detectable)
    assert set(co) == set(detectable)
    assert excluded == []
