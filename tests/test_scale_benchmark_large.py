"""Gate 2b — unit tests for the large-scale benchmark's graph replication.

Covers the deterministic graph-replication and subject-counting helpers (no
Oxigraph run), so they are fast. The full 1k/2k/5k sweep is exercised by running
``scripts/run_scale_benchmark_large.py`` and recorded in
eval/scale_benchmark_large.json.
"""
from __future__ import annotations

from rdflib import Graph, Literal, URIRef

from kg.ontology import CAVE
from scripts.run_scale_benchmark_large import _count_subjects, _replicate


def _one_subject_graph() -> Graph:
    g = Graph()
    g.bind("cave", CAVE)
    subj = URIRef("https://cave-onc.org/shacl/RS/S1/1")
    g.add((subj, CAVE.USUBJID, Literal("S1")))
    g.add((subj, CAVE.RSTESTCD, Literal("OVRLRESP")))
    return g


def test_count_subjects():
    assert _count_subjects(_one_subject_graph()) == 1


def test_replicate_multiplies_subjects():
    base = _one_subject_graph()
    scaled = _replicate(base, 5)
    assert _count_subjects(scaled) == 5
    # replicas carry distinct USUBJIDs
    usubjids = {str(o) for _s, _p, o in scaled.triples((None, CAVE.USUBJID, None))}
    assert len(usubjids) == 5


def test_replicate_factor_one_is_identity():
    base = _one_subject_graph()
    assert _replicate(base, 1) is base


def test_replicate_suffixes_all_usubjid_predicates():
    """Both cave: and cdisc: USUBJID literals must be distinct per replica."""
    import rdflib
    CDISC = rdflib.Namespace("http://www.cdisc.org/ns/sdtm#")
    g = _one_subject_graph()
    subj = URIRef("https://cave-onc.org/shacl/RS/S1/1")
    g.add((subj, CDISC.USUBJID, Literal("S1")))
    scaled = _replicate(g, 3)
    cdisc_ids = {str(o) for _s, _p, o in scaled.triples((None, CDISC.USUBJID, None))}
    assert len(cdisc_ids) == 3  # not collapsed to one


def test_loglog_fit_recovers_known_slope():
    """`loglog_slope` must recover a known power-law exponent with R^2 = 1."""
    from scripts.run_scale_benchmark_large import loglog_slope

    # y = x^0.5 exactly -> log-log slope 0.5, perfect fit.
    results = [{"subjects": s, "sparql_query_s": s ** 0.5}
               for s in (1000, 2000, 5000)]
    slope, r2 = loglog_slope(results, "sparql_query_s")
    assert abs(slope - 0.5) < 1e-3
    assert abs(r2 - 1.0) < 1e-6


def test_loglog_fit_flags_superlinear():
    """A super-linear series (exponent >1) must not be reported as sub-linear."""
    from scripts.run_scale_benchmark_large import loglog_slope

    results = [{"subjects": s, "sparql_query_s": s ** 1.3}
               for s in (1000, 2000, 5000)]
    slope, _ = loglog_slope(results, "sparql_query_s")
    assert slope > 1.0
