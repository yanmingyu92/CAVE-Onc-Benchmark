"""Gate 2a — single-pass hardening of contradiction archetype shapes.

Focus: A03 (treatment-related AE precedes first exposure). The v3 shape is
absolutely specific — it fires on the true contradiction (a related AE before
the subject's earliest exposure) but NOT on the benign multi-cycle pattern
(a later-cycle exposure that legitimately follows an early treatment AE), which
was the source of the 121 clean-data false positives eliminated in Gate 2a.

These tests validate the SHACL shape directly on minimal synthetic graphs, so
they run in well under a second (no full-cohort validation).
"""
from __future__ import annotations

from pathlib import Path

import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, SH, XSD
from pyshacl import validate as shacl_validate

CAVE = rdflib.Namespace("https://cave-onc.org/shacl/")
SHAPES = Path("shacl/archetype_shapes.ttl")


def _data_graph() -> rdflib.Graph:
    """A data graph with the prefix bindings the SHACL-SPARQL body relies on.

    pyShACL evaluates the constraint query against the data graph, so ``cave:``
    and ``xsd:`` must be bound here exactly as the production graph builder does.
    """
    g = rdflib.Graph()
    g.bind("cave", CAVE)
    g.bind("xsd", XSD)
    return g


def _a03_shape_graph() -> rdflib.Graph:
    """Load the archetype shapes (prefix bindings intact for the SPARQL body).

    A03 is the only archetype shape whose sh:targetClass is cave:EX, so on a
    graph that contains only EX/AE nodes it is the only shape that can fire.
    """
    return rdflib.Graph().parse(str(SHAPES), format="turtle")


def _subject_ex(g: rdflib.Graph, usubjid: str, seq: int, exstdtc: str) -> None:
    node = CAVE[f"EX/{usubjid}/{seq}"]
    g.add((node, RDF.type, CAVE.EX))
    g.add((node, CAVE.USUBJID, Literal(usubjid)))
    g.add((node, CAVE.EXSTDTC, Literal(exstdtc)))


def _subject_ae(g: rdflib.Graph, usubjid: str, seq: int, aestdtc: str, rel: str) -> None:
    node = CAVE[f"AE/{usubjid}/{seq}"]
    g.add((node, RDF.type, CAVE.AE))
    g.add((node, CAVE.USUBJID, Literal(usubjid)))
    g.add((node, CAVE.AESTDTC, Literal(aestdtc)))
    g.add((node, CAVE.AEREL, Literal(rel)))


def _fired_subjects(data: rdflib.Graph) -> set[str]:
    conforms, report, _ = shacl_validate(
        data, shacl_graph=_a03_shape_graph(), inference="none",
    )
    subs: set[str] = set()
    for vr in report.subjects(RDF.type, SH.ValidationResult):
        focus = next(report.objects(vr, SH.focusNode), None)
        if focus is not None:
            subs.add(str(focus).rsplit("/", 2)[-2])
    return subs


def test_a03_fires_on_related_ae_before_first_exposure():
    """Contradiction: earliest exposure post-dates a treatment-related AE."""
    g = _data_graph()
    _subject_ae(g, "SUBJ-CONTRA", 1, "2020-01-03", "PROBABLE")
    _subject_ex(g, "SUBJ-CONTRA", 1, "2020-01-20")  # first dose 17d AFTER the AE
    _subject_ex(g, "SUBJ-CONTRA", 2, "2020-02-20")
    assert "SUBJ-CONTRA" in _fired_subjects(g)


def test_a03_silent_on_benign_multicycle_exposure():
    """Benign: first dose precedes the AE; a later cycle follows it (was 121 FPs)."""
    g = _data_graph()
    _subject_ex(g, "SUBJ-OK", 1, "2020-01-01")   # first dose BEFORE the AE
    _subject_ae(g, "SUBJ-OK", 1, "2020-01-10", "PROBABLE")
    _subject_ex(g, "SUBJ-OK", 2, "2020-02-01")   # later cycle after the AE — legitimate
    _subject_ex(g, "SUBJ-OK", 3, "2020-03-01")
    assert "SUBJ-OK" not in _fired_subjects(g)


def test_a03_silent_on_unrelated_ae_before_first_exposure():
    """An AE with no causal attribution (NONE/REMOTE) is not a contradiction."""
    g = _data_graph()
    _subject_ae(g, "SUBJ-UNREL", 1, "2020-01-03", "NONE")
    _subject_ex(g, "SUBJ-UNREL", 1, "2020-01-20")
    assert "SUBJ-UNREL" not in _fired_subjects(g)


def test_a03_respects_seven_day_tolerance():
    """A related AE within 7 days of first exposure is within tolerance (no flag)."""
    g = _data_graph()
    _subject_ae(g, "SUBJ-TOL", 1, "2020-01-15", "POSSIBLE")
    _subject_ex(g, "SUBJ-TOL", 1, "2020-01-20")  # only 5 days after the AE
    assert "SUBJ-TOL" not in _fired_subjects(g)


def test_a03_month_boundary_gap_is_calendar_correct():
    """AE 2020-01-25 -> EX 2020-02-02 is a true 8-day gap and must fire.

    The old Y*365+M*30+D approximation computed this as 7 days and (wrongly)
    stayed silent; the Julian-Day-Number arithmetic is calendar-correct.
    """
    g = _data_graph()
    _subject_ae(g, "SUBJ-BND", 1, "2020-01-25", "PROBABLE")
    _subject_ex(g, "SUBJ-BND", 1, "2020-02-02")  # true gap = 8 days (>7)
    assert "SUBJ-BND" in _fired_subjects(g)


def test_a03_month_boundary_within_tolerance_stays_silent():
    """AE 2020-01-28 -> EX 2020-02-02 is a true 5-day gap and must NOT fire."""
    g = _data_graph()
    _subject_ae(g, "SUBJ-BND2", 1, "2020-01-28", "PROBABLE")
    _subject_ex(g, "SUBJ-BND2", 1, "2020-02-02")  # true gap = 5 days (<=7)
    assert "SUBJ-BND2" not in _fired_subjects(g)


# ── Single-pass detection path (no clean-baseline delta) ───────────────────

def test_single_pass_helper_reports_flagged_subject():
    """`_flagged_subjects_by_archetype` maps an archetype to its flagged subjects.

    This is the primitive the single-pass path uses instead of a clean-baseline
    delta: it reads per-subject archetype flags straight from the audit trace.
    """
    from scripts.track_b_analysis import _flagged_subjects_by_archetype

    g = _data_graph()
    _subject_ae(g, "SUBJ-CONTRA", 1, "2020-01-03", "PROBABLE")
    _subject_ex(g, "SUBJ-CONTRA", 1, "2020-01-20")
    flagged = _flagged_subjects_by_archetype(g, backend="pyshacl")
    assert "SUBJ-CONTRA" in flagged.get("A03", set())


def test_flag_counts_vs_subjects_distinction():
    """`_flag_counts_by_archetype` counts flags (rows); >= distinct subjects."""
    from scripts.track_b_analysis import (
        _flag_counts_by_archetype, _flagged_subjects_by_archetype,
    )

    g = _data_graph()
    # One subject, two exposures both earliest-tied and both after a related AE:
    _subject_ae(g, "SUBJ-M", 1, "2020-01-03", "PROBABLE")
    _subject_ex(g, "SUBJ-M", 1, "2020-01-20")
    _subject_ex(g, "SUBJ-M", 2, "2020-01-20")  # tie for earliest -> 2 flags
    flags = _flag_counts_by_archetype(g, backend="pyshacl")
    subjects = _flagged_subjects_by_archetype(g, backend="pyshacl")
    assert flags.get("A03", 0) >= len(subjects.get("A03", set()))
    assert len(subjects.get("A03", set())) == 1  # still one distinct subject


def test_subject_subframes_restricts_to_one_subject():
    """`_subject_subframes` keeps only the target subject's rows + design domains."""
    import pandas as pd
    from scripts.track_b_analysis import _subject_subframes

    frames = {
        "DM": pd.DataFrame({"USUBJID": ["S1", "S2"], "ARMCD": ["A", "B"]}),
        "TA": pd.DataFrame({"ARMCD": ["A", "B"], "ARM": ["Arm A", "Arm B"]}),
    }
    out = _subject_subframes(frames, "S1")
    assert list(out["DM"]["USUBJID"]) == ["S1"]
    assert len(out["TA"]) == 2  # trial-design domain kept whole
