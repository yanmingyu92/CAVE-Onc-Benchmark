"""Tests for agent/orchestrator.py and agent/table7.py — T5.5 LangGraph L3 orchestrator."""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from agent.orchestrator import AgentState, CaveAgent, VendorRouter
from agent.table7 import lookup_table7
from audit.trace_schema import TraceEntry

# -- Namespace constants (mirroring orchestrator) -------------------------------

CDISC = "http://www.cdisc.org/ns/sdtm#"
CAVE = "https://cave-onc.org/shacl/"


def _build_rs_graph(
    usubjid: str = "SUBJ001",
    records: list[tuple[str, str, str]] | None = None,
    has_new_lesion_tu: bool = False,
) -> Graph:
    """Build a minimal RDF graph with RS (and optional TU) records.

    Parameters
    ----------
    records : list of (visit, testcd, orres)
    has_new_lesion_tu : if True, add a TU record with a new-lesion flag

    Note: Emits data using CAVE namespace to match xpt_to_rdf.py output,
    with CDISC USUBJID as fallback (mirroring the adapter's dual emission).
    """
    g = Graph()
    # Use CAVE namespace (matching xpt_to_rdf.py output)
    rs_type = URIRef(f"{CAVE}RS")
    usubjid_prop_cave = URIRef(f"{CAVE}USUBJID")
    usubjid_prop_cdisc = URIRef(f"{CDISC}USUBJID")
    testcd_prop = URIRef(f"{CAVE}RSTESTCD")
    orres_prop = URIRef(f"{CAVE}RSORRES")
    visit_prop = URIRef(f"{CAVE}VISITNUM")

    default_records = [
        ("1", "OVRLRESP", "CR"),
        ("1", "NTOVRLRESP", "CR"),
        ("1", "NEWLEC", "N"),
    ]
    for i, (visit, testcd, orres) in enumerate(records or default_records):
        subj = URIRef(f"http://www.cdisc.org/ns/cave-onc#RS/{usubjid}/{i}")
        g.add((subj, RDF.type, rs_type))
        g.add((subj, usubjid_prop_cave, Literal(usubjid)))
        g.add((subj, usubjid_prop_cdisc, Literal(usubjid)))
        g.add((subj, testcd_prop, Literal(testcd)))
        g.add((subj, orres_prop, Literal(orres)))
        g.add((subj, visit_prop, Literal(visit)))

    if has_new_lesion_tu:
        tu_type = URIRef(f"{CAVE}TU")
        tu_test_prop = URIRef(f"{CAVE}TUTESTCD")
        tu_subj = URIRef(f"http://www.cdisc.org/ns/cave-onc#TU/{usubjid}/1")
        g.add((tu_subj, RDF.type, tu_type))
        g.add((tu_subj, usubjid_prop_cave, Literal(usubjid)))
        g.add((tu_subj, tu_test_prop, Literal("NEW LESION")))

    return g


# -- Tests ---------------------------------------------------------------------


def test_agent_instantiation():
    """CaveAgent can be instantiated with default and custom VendorRouter."""
    agent_default = CaveAgent()
    assert agent_default.router is not None
    assert agent_default.router.vendor_primary == "deepseek"

    router = VendorRouter(vendor_primary="glm")
    agent_custom = CaveAgent(vendor_router=router)
    assert agent_custom.router.vendor_primary == "glm"


def test_table7_lookup_correctness():
    """Table 7 lookup returns correct expected overall for known cases."""
    assert lookup_table7("CR", "CR", "NO") == "CR"
    assert lookup_table7("PR", "NON-CR/NON-PD", "NO") == "PR"
    assert lookup_table7("SD", "NON-CR/NON-PD", "NO") == "SD"
    assert lookup_table7("CR", "NON-CR/NON-PD", "NO") == "PR"
    assert lookup_table7("CR", "CR", "YES") == "PD"
    assert lookup_table7("PR", "CR", "YES") == "PD"
    assert lookup_table7("SD", "PD", "NO") == "PD"
    assert lookup_table7("NE", "PD", "NO") == "PD"
    # Unknown combination returns None
    assert lookup_table7("UNKNOWN", "CR", "NO") is None


def test_table7_case_insensitive():
    """Table 7 lookup normalises case."""
    assert lookup_table7("cr", "cr", "no") == "CR"
    assert lookup_table7("Pr", "Non-CR/Non-PD", "No") == "PR"


def test_agent_detects_a19_contradiction():
    """Agent emits a TraceEntry when overall response contradicts Table 7."""
    # Target=PR, Non-target=SD, No new lesion → expected PR, but actual=CR
    g = _build_rs_graph(
        usubjid="SUBJ001",
        records=[
            ("1", "OVRLRESP", "CR"),        # actual overall = CR (contradiction)
            ("1", "NTOVRLRESP", "NON-CR/NON-PD"),
            ("1", "NEWLEC", "N"),
        ],
    )
    agent = CaveAgent()
    traces = agent.run(g)
    assert len(traces) >= 1
    trace = traces[0]

    assert trace["layer"] == "L3"
    assert trace["archetype"] == "A19"
    assert trace["severity"] == "violation"
    assert trace["subject"] == "SUBJ001"
    assert trace["agent_trace"]["expected"] == "PR"
    assert trace["agent_trace"]["actual"] == "CR"


def test_agent_passes_clean_data():
    """Agent emits no traces when overall response matches Table 7."""
    # Target=CR, Non-target=CR, No new lesion → expected CR, actual=CR (clean)
    g = _build_rs_graph(
        usubjid="SUBJ002",
        records=[
            ("1", "OVRLRESP", "CR"),
            ("1", "NTOVRLRESP", "CR"),
            ("1", "NEWLEC", "N"),
        ],
    )
    agent = CaveAgent()
    traces = agent.run(g)
    assert len(traces) == 0


def test_trace_entry_emission_layer_l3():
    """Emitted TraceEntry has layer='L3' and correct field structure."""
    # Target=SD, Non-target=PD, No → expected=PD, actual=SD (contradiction)
    g = _build_rs_graph(
        usubjid="SUBJ003",
        records=[
            ("1", "OVRLRESP", "SD"),
            ("1", "NTOVRLRESP", "PD"),
            ("1", "NEWLEC", "N"),
        ],
    )
    agent = CaveAgent()
    traces = agent.run(g)
    assert len(traces) == 1

    # Verify the TraceEntry can be reconstructed
    entry = TraceEntry(**traces[0])
    assert entry.layer == "L3"
    assert entry.archetype == "A19"
    assert entry.severity == "violation"
    assert entry.agent_trace is not None
    assert entry.agent_trace["expected"] == "PD"
    assert entry.agent_trace["actual"] == "SD"
    assert len(entry.evidence_path) >= 4


def test_agent_new_lesion_triggers_pd():
    """Agent correctly flags PD when new lesion is present regardless of target."""
    # Target=CR, Non-target=CR, but new lesion=YES → expected PD, actual=CR
    g = _build_rs_graph(
        usubjid="SUBJ004",
        records=[
            ("1", "OVRLRESP", "CR"),
            ("1", "NTOVRLRESP", "CR"),
            ("1", "NEWLEC", "Y"),
        ],
    )
    agent = CaveAgent()
    traces = agent.run(g)
    assert len(traces) == 1
    assert traces[0]["agent_trace"]["expected"] == "PD"
    assert traces[0]["agent_trace"]["actual"] == "CR"
