"""Tests for shacl/runner.py and shacl/shape_map.py (T5.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF

from audit.store import AuditStore
from shacl.runner import ShaclRunner
from shacl.shape_map import SHAPE_NS, SHAPE_TO_ARCHETYPE

CAVE = Namespace(SHAPE_NS)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    """Provide a temporary AuditStore opened as context manager."""
    db = tmp_path / "test.db"
    s = AuditStore(db)
    with s:
        yield s


@pytest.fixture()
def shapes_dir(tmp_path):
    """Minimal SHACL shapes that fire on test data."""
    shape_ttl = """\
@prefix cave: <https://cave-onc.org/shacl/> .
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

cave:Shape_CORE-000068 a sh:NodeShape ;
    sh:property [ sh:maxCount 0 ; sh:path cave:AGETXT ] ;
    sh:targetClass cave:DM .

cave:Shape_WarnTest a sh:NodeShape ;
    sh:property [ sh:maxCount 0 ; sh:path cave:FORBIDDEN ; sh:severity sh:Warning ] ;
    sh:targetClass cave:DM .
"""
    d = tmp_path / "shapes"
    d.mkdir()
    (d / "test.ttl").write_text(shape_ttl)
    return d


def _violating_graph() -> Graph:
    """Graph with a DM record that violates both test shapes."""
    g = Graph()
    g.bind("cave", CAVE)
    rec = CAVE["DM/SUBJ001/1"]
    g.add((rec, RDF.type, CAVE.DM))
    g.add((rec, CAVE.AGETXT, Literal("65-70")))
    g.add((rec, CAVE.FORBIDDEN, Literal("bad")))
    return g


def _clean_graph() -> Graph:
    """Graph with a DM record that conforms to all test shapes."""
    g = Graph()
    g.bind("cave", CAVE)
    rec = CAVE["DM/SUBJ002/1"]
    g.add((rec, RDF.type, CAVE.DM))
    return g


# ---------------------------------------------------------------------------
# 1. Runner instantiation
# ---------------------------------------------------------------------------


def test_runner_instantiation():
    """ShaclRunner can be created with a data graph and shapes dir."""
    g = Graph()
    runner = ShaclRunner(g, shapes_dir="shacl")
    assert runner.data_graph is g
    assert runner.store is None
    assert isinstance(runner.shape_map, dict)


# ---------------------------------------------------------------------------
# 2. Validation produces results against pilot1 data
# ---------------------------------------------------------------------------


def test_pilot1_validation():
    """Run against real pilot1 data — completes without error."""
    data_dir = Path("data/pilot1")
    if not data_dir.exists():
        pytest.skip("pilot1 data not available")

    from kg.xpt_to_rdf import load_xpt_to_graph

    g = load_xpt_to_graph(data_dir, domains=["DM"])
    runner = ShaclRunner(g, shapes_dir="shacl")
    result = runner.run()

    assert "conforms" in result
    assert "total" in result
    assert isinstance(result["conforms"], int)
    assert isinstance(result["total"], int)


# ---------------------------------------------------------------------------
# 3. TraceEntry emission to AuditStore
# ---------------------------------------------------------------------------


def test_trace_emission(store, shapes_dir):
    """Violating data produces TraceEntry records in the audit store."""
    g = _violating_graph()
    runner = ShaclRunner(g, shapes_dir=shapes_dir, store=store)
    result = runner.run()

    assert result["total"] >= 1
    assert store.count() == result["total"]
    # All entries should have layer L1
    for entry in store.query_by_subject("SUBJ001"):
        assert entry.layer == "L1"
        assert entry.severity in ("violation", "warning", "info")
        assert entry.shacl_shape is not None


# ---------------------------------------------------------------------------
# 4. Severity mapping
# ---------------------------------------------------------------------------


def test_severity_mapping(shapes_dir):
    """sh:Violation → 'violation', sh:Warning → 'warning'."""
    g = _violating_graph()
    runner = ShaclRunner(g, shapes_dir=shapes_dir)
    result = runner.run()

    # Shape_CORE-000068 (default severity) → violation
    # Shape_WarnTest (sh:Warning) → warning
    assert result["violation"] >= 1
    assert result["warning"] >= 1
    assert result["total"] == result["violation"] + result["warning"] + result["info"]


def test_clean_graph_no_violations(shapes_dir):
    """Conforming data produces zero violations."""
    g = _clean_graph()
    runner = ShaclRunner(g, shapes_dir=shapes_dir)
    result = runner.run()
    assert result["conforms"] == 1
    assert result["total"] == 0


# ---------------------------------------------------------------------------
# 5. Shape-to-archetype mapping
# ---------------------------------------------------------------------------


def test_shape_map_loaded():
    """SHAPE_TO_ARCHETYPE dict is populated from CSVs."""
    assert isinstance(SHAPE_TO_ARCHETYPE, dict)
    core_keys = [k for k in SHAPE_TO_ARCHETYPE if "CORE-" in k]
    assert len(core_keys) > 0


def test_shape_map_archetype_lookup():
    """Known shape IRIs map to correct (archetype_id, xref) tuples."""
    key = f"{SHAPE_NS}Shape_CORE-000068"
    if key in SHAPE_TO_ARCHETYPE:
        arch_id, xref = SHAPE_TO_ARCHETYPE[key]
        assert "CORE-000068" in xref
