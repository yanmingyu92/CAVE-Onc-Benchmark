"""Tests for kg/xpt_to_rdf.py and kg/ontology.py (T5.1)."""

from __future__ import annotations

from pathlib import Path

import pyreadstat
import pytest
from rdflib import RDF

from kg.ontology import CDISC, CAVE, domain_class, domain_property
from kg.xpt_to_rdf import load_xpt_to_graph

DATA = Path(__file__).resolve().parent.parent / "data"
PILOT1 = DATA / "pilot1"
ONCO = DATA / "pharmaversesdtm_onco"


# -- Shared fixture graph -----------------------------------------------------

@pytest.fixture(scope="module")
def graph():
    """Load pilot1 DM+EX and pharmaversesdtm_onco TU/TR/RS + pilot1 RELREC."""
    return load_xpt_to_graph(
        PILOT1 / "dm.xpt",
        PILOT1 / "ex.xpt",
        ONCO,
        PILOT1 / "relrec.xpt",
        domains=["DM", "EX", "TU", "TR", "RS"],
    )


# 1. Smoke load — graph is non-empty
def test_graph_nonempty(graph):
    assert len(graph) > 0, "Graph should contain triples"


# 2. Triple count — sanity bound
def test_triple_count(graph):
    n = len(graph)
    assert n > 500, f"Expected >500 triples, got {n}"


# 3. Domain-specific types exist (uses CAVE namespace after alignment)
def test_domain_types(graph):
    for domain in ("DM", "EX", "TU", "TR", "RS"):
        cls = CAVE[domain]
        subjects = list(graph.subjects(RDF.type, cls))
        assert len(subjects) > 0, f"No instances of {cls}"


# 4. USUBJID cross-domain linkage — same USUBJID appears in multiple domains
def test_usubjid_cross_domain(graph):
    usubjids_dm = set(str(o) for o in graph.objects(None, CDISC.USUBJID)
                      if _subj_type(graph, o, "DM"))
    # Get EX USUBJIDs via triple patterns
    usubjids_ex = set()
    for s in graph.subjects(RDF.type, CAVE["EX"]):
        for o in graph.objects(s, CDISC.USUBJID):
            usubjids_ex.add(str(o))
    overlap = usubjids_dm & usubjids_ex
    assert len(overlap) > 0, "Expected shared USUBJIDs between DM and EX"


# 5. Round-trip subject count matches pyreadstat row count
def test_row_count_roundtrip():
    df, _ = pyreadstat.read_xport(str(PILOT1 / "dm.xpt"))
    g = load_xpt_to_graph(PILOT1 / "dm.xpt", domains=["DM"])
    dm_instances = set(g.subjects(RDF.type, CAVE["DM"]))
    assert len(dm_instances) == len(df), (
        f"DM instance count {len(dm_instances)} != DataFrame rows {len(df)}"
    )


# 6. RELREC triples present
def test_relrec_triples(graph):
    relrec_types = list(graph.subjects(RDF.type, CDISC.RelatedRecords))
    assert len(relrec_types) > 0, "Expected RELREC relationship triples"
    # Check a RELREC has RDOMAIN
    first = relrec_types[0]
    rdomains = list(graph.objects(first, CDISC.RDOMAIN))
    assert len(rdomains) > 0, "RELREC should have RDOMAIN"


# -- Helpers ------------------------------------------------------------------

def _subj_type(graph, usubjid_val, domain: str) -> bool:
    """Check if any subject with the given USUBJID has the domain type."""
    for s in graph.subjects(CDISC.USUBJID, usubjid_val):
        if (s, RDF.type, CAVE[domain]) in graph:
            return True
    return False
