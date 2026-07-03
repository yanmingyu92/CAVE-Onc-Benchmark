"""Tests for the Oxigraph hybrid L1 backend (shacl/oxigraph_runner.py)."""
from __future__ import annotations

from pathlib import Path

import pytest
import rdflib

SHAPES_DIR = Path("shacl")
FIXTURE = Path("tests/fixtures/recist_synthetic.ttl")


def test_no_shape_file_mixes_sparql_and_property():
    """Oxigraph backend assumes each *.ttl is pure SPARQL or pure structural."""
    mixed = []
    for ttl in sorted(SHAPES_DIR.glob("*.ttl")):
        text = ttl.read_text(encoding="utf-8")
        if "sh:sparql" in text and "sh:property" in text:
            mixed.append(ttl.name)
    assert not mixed, f"shape files mix sh:sparql and sh:property: {mixed}"


def test_extract_sparql_constraints_count_and_fields():
    from shacl.oxigraph_runner import extract_sparql_constraints

    constraints = extract_sparql_constraints(SHAPES_DIR)
    # 18 archetype (archetype_shapes.ttl) + 8 RECIST (recist_derivation.ttl)
    assert len(constraints) == 26

    by_iri = {c.shape_iri: c for c in constraints}
    # every constraint has a non-empty SELECT and a PREFIX header injected
    for c in constraints:
        assert "SELECT" in c.select
        assert "PREFIX cave:" in c.select
        assert c.severity in {"violation", "warning", "info"}

    # S7 confirmation is a Warning; A01 is a Violation with target class cave:RS
    s7 = by_iri["https://cave-onc.org/shacl/Shape_RECIST_S7_confirmation"]
    assert s7.severity == "warning"
    a01 = by_iri["https://cave-onc.org/shacl/Shape_Archetype_A01"]
    assert a01.severity == "violation"
    assert a01.target_class == "https://cave-onc.org/shacl/RS"


def test_extract_usubjid_helper_matches_iri_parse():
    from rdflib import Graph
    from shacl.runner import extract_usubjid

    g = Graph()
    focus = "https://cave-onc.org/RS/SUBJ-001/3"
    # no cdisc:USUBJID triple -> falls back to IRI parse (parts[-2])
    assert extract_usubjid(g, focus) == "SUBJ-001"


def test_oxigraph_runner_detects_recist_on_fixture():
    from audit.store import AuditStore, _row_to_entry
    from shacl.oxigraph_runner import OxigraphSparqlRunner

    g = rdflib.Graph()
    g.parse(str(FIXTURE), format="turtle")

    with AuditStore(":memory:") as store:
        counts = OxigraphSparqlRunner(g, shapes_dir="shacl", store=store).run()
        rows = store._conn.execute(
            "SELECT * FROM traces ORDER BY rowid ASC"
        ).fetchall()
        entries = [_row_to_entry(r).model_dump() for r in rows]

    # The synthetic fixture yields S3 (1 violation) + S7 (2 warnings) from the
    # SPARQL detectors. NB: Oxigraph yields 2 S7 warnings, not the 3 pyShACL
    # reports — Oxigraph correctly evaluates the 28-day confirmation duration
    # (SUBJ-A V2->V3 = 42 days >= P28D, so V2 is confirmed and NOT flagged),
    # whereas rdflib cannot compare xsd:dayTimeDuration values and spuriously
    # flags SUBJ-A_V2. See test_oxigraph_fixes_rdflib_duration_bug_on_s7.
    assert counts["total"] == 3
    shapes = {e["shacl_shape"].split("/")[-1] for e in entries}
    assert "Shape_RECIST_S7_confirmation" in shapes
    assert "Shape_RECIST_S3_target_pr" in shapes
    # severities recorded correctly
    sev = {e["shacl_shape"].split("/")[-1]: e["severity"] for e in entries}
    assert sev["Shape_RECIST_S7_confirmation"] == "warning"
    assert sev["Shape_RECIST_S3_target_pr"] == "violation"


def test_shaclrunner_oxigraph_backend_runs_both_passes():
    from audit.store import AuditStore, _row_to_entry
    from shacl.runner import ShaclRunner

    g = rdflib.Graph()
    g.parse(str(FIXTURE), format="turtle")

    with AuditStore(":memory:") as store:
        counts = ShaclRunner(
            g, shapes_dir="shacl", store=store, backend="oxigraph"
        ).run()
        rows = store._conn.execute(
            "SELECT * FROM traces ORDER BY rowid ASC"
        ).fetchall()
        entries = [_row_to_entry(r).model_dump() for r in rows]

    shapes = {e["shacl_shape"].split("/")[-1] for e in entries}
    # SPARQL detectors fired via Oxigraph
    assert "Shape_RECIST_S7_confirmation" in shapes
    # total count matches emitted traces (structural + sparql merged, hash-chained)
    assert counts["total"] == len(entries)


def test_shaclrunner_invalid_backend_raises():
    from shacl.runner import ShaclRunner

    g = rdflib.Graph()
    with pytest.raises(ValueError):
        ShaclRunner(g, backend="nonsense").run()


# ── Equivalence (keystone: guards Track B 20/20) ──────────────────────────

S7_SHAPE = "Shape_RECIST_S7_confirmation"
BENCH = Path("data/pharmaversesdtm_recist")


def _sparql_flags(graph, backend):
    """Sorted (subject, archetype, shape, severity) tuples for SPARQL-shape flags."""
    from audit.store import AuditStore, _row_to_entry
    from shacl.oxigraph_runner import extract_sparql_constraints
    from shacl.runner import ShaclRunner

    sparql_iris = {c.shape_iri for c in extract_sparql_constraints("shacl")}
    with AuditStore(":memory:") as store:
        ShaclRunner(graph, shapes_dir="shacl", store=store, backend=backend).run()
        rows = store._conn.execute(
            "SELECT * FROM traces ORDER BY rowid ASC"
        ).fetchall()
    flags = []
    for r in rows:
        e = _row_to_entry(r).model_dump()
        if e["shacl_shape"] in sparql_iris:
            flags.append(
                (
                    e["subject"],
                    e["archetype"],
                    e["shacl_shape"].split("/")[-1],
                    e["severity"],
                )
            )
    return sorted(flags)


def test_oxigraph_equivalent_to_pyshacl_on_fixture_excluding_s7():
    """Where both engines agree, the two backends produce identical SPARQL flags."""
    from collections import Counter

    g1 = rdflib.Graph(); g1.parse(str(FIXTURE), format="turtle")
    g2 = rdflib.Graph(); g2.parse(str(FIXTURE), format="turtle")
    py = [f for f in _sparql_flags(g1, "pyshacl") if f[2] != S7_SHAPE]
    ox = [f for f in _sparql_flags(g2, "oxigraph") if f[2] != S7_SHAPE]
    assert len(py) >= 1, "baseline must be non-trivial"
    assert Counter(py) == Counter(ox), f"divergence:\n  py={py}\n  ox={ox}"


def test_oxigraph_fixes_rdflib_duration_bug_on_s7():
    """Oxigraph correctly evaluates the 28-day confirmation; rdflib cannot.

    For SUBJ-A, V2(PR,2025-02-01)->V3(CR,2025-03-15) = 42 days >= P28D, so V2 is
    confirmed and must NOT be flagged. rdflib returns unbound for the
    dayTimeDuration comparison and spuriously flags V2; Oxigraph suppresses it.
    """
    g1 = rdflib.Graph(); g1.parse(str(FIXTURE), format="turtle")
    g2 = rdflib.Graph(); g2.parse(str(FIXTURE), format="turtle")
    py_s7 = [f for f in _sparql_flags(g1, "pyshacl") if f[2] == S7_SHAPE]
    ox_s7 = [f for f in _sparql_flags(g2, "oxigraph") if f[2] == S7_SHAPE]
    assert len(py_s7) == 3  # rdflib: 3 (incl. 1 spurious)
    assert len(ox_s7) == 2  # oxigraph: 2 (spec-correct)


@pytest.mark.skipif(
    not (BENCH / "rs.xpt").exists(),
    reason="benchmark data absent (gitignored)",
)
def test_oxigraph_equivalent_on_injected_archetype(tmp_path):
    """On injected A02 data, both backends detect A02 and agree on all SPARQL flags."""
    from collections import Counter

    from bench.injector import Injector
    from kg.xpt_to_rdf import load_xpt_to_graph

    Injector(output_dir=str(tmp_path)).inject("A02")
    data_dir = tmp_path / "A02"

    g1 = load_xpt_to_graph(data_dir)
    g2 = load_xpt_to_graph(data_dir)
    py = _sparql_flags(g1, "pyshacl")
    ox = _sparql_flags(g2, "oxigraph")

    assert Counter(py) == Counter(ox), (
        f"backend divergence on injected A02:\n  py={py}\n  ox={ox}"
    )
    assert any(f[1] == "A02" for f in ox), "A02 must be detected on injected data"
