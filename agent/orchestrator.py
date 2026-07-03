"""LangGraph L3 orchestrator — CAVE agent for A19 (Table 7 contradiction).

2-layer architecture (T3.3 decision): 19 archetypes → L1 SHACL;
A19 only → L3 agent (this file).  Fully deterministic for A19 — no LLM
calls needed.  A dual-vendor router is scaffolded for future archetypes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from agent.table7 import lookup_table7
from audit.trace_schema import create_trace_entry

logger = logging.getLogger(__name__)

CDISC = "http://www.cdisc.org/ns/sdtm#"
CAVE = "https://cave-onc.org/shacl/"

# RS test codes
TARGET_TEST = "OVRLRESP"
NONTARGET_TEST = "NTOVRLRESP"
NEWLEC_TEST = "NEWLEC"

_RESET: dict = dict(
    current_subject="", target_response=None, nontarget_response=None,
    new_lesion_status=None, expected_overall=None, actual_overall=None,
    is_contradiction=False,
)


@dataclass
class AgentState:
    """State flowing through the LangGraph nodes."""
    data_graph: Any = None
    l1_results: dict = field(default_factory=dict)
    subjects: list[str] = field(default_factory=list)
    current_subject: str = ""
    current_visit: str = ""
    target_response: str | None = None
    nontarget_response: str | None = None
    new_lesion_status: str | None = None
    expected_overall: str | None = None
    actual_overall: str | None = None
    is_contradiction: bool = False
    traces: list[dict] = field(default_factory=list)


@dataclass
class VendorRouter:
    """Placeholder for DeepSeek / GLM dual-vendor routing (no real API)."""
    vendor_primary: Literal["deepseek", "glm"] = "deepseek"
    vendor_secondary: Literal["deepseek", "glm"] | None = None
    divergence_threshold: float = 0.05

    def call(self, prompt: str, vendor: str | None = None) -> str:
        return ""


# -- RDF helpers ----------------------------------------------------------------

def _obj(g: Graph, subj: URIRef, prop: str) -> str:
    # Try CAVE namespace first (xpt_to_rdf emits bare cave:VAR properties)
    for o in g.objects(subj, URIRef(f"{CAVE}{prop}")):
        return str(o)
    # Fallback to CDISC namespace
    for o in g.objects(subj, URIRef(f"{CDISC}{prop}")):
        return str(o)
    return ""


def _rs_records(g: Graph, usubjid: str) -> list[tuple[str, str, str]]:
    """Return [(visit, testcd, orres)] for RS records of a subject."""
    out: list[tuple[str, str, str]] = []
    # xpt_to_rdf emits cave:RS (not cdisc:RS), and bare cave:PROP (not cdisc:RS-PROP)
    for s in g.subjects(RDF.type, URIRef(f"{CAVE}RS")):
        subj_id = _obj(g, s, "USUBJID")
        if subj_id != usubjid:
            continue
        out.append((
            _obj(g, s, "VISITNUM"),
            _obj(g, s, "RSTESTCD"),
            _obj(g, s, "RSORRES"),
        ))
    return out


def _has_new_lesion(g: Graph, usubjid: str) -> bool:
    for s in g.subjects(RDF.type, URIRef(f"{CAVE}TU")):
        if _obj(g, s, "USUBJID") != usubjid:
            continue
        for v in g.objects(s, URIRef(f"{CAVE}TUTESTCD")):
            if "NEW" in str(v).upper():
                return True
        for v in g.objects(s, URIRef(f"{CAVE}TUTEST")):
            if "NEW" in str(v).upper():
                return True
    return False


# -- LangGraph nodes ------------------------------------------------------------

def receive_l1_results(state: AgentState) -> dict:
    g: Graph = state.data_graph
    if g is None:
        return {"subjects": []}
    subjects: set[str] = set()
    for s in g.subjects(RDF.type, URIRef(f"{CAVE}RS")):
        for v in g.objects(s, URIRef(f"{CAVE}USUBJID")):
            subjects.add(str(v))
        # Fallback to CDISC namespace
        if not subjects:
            for v in g.objects(s, URIRef(f"{CDISC}USUBJID")):
                subjects.add(str(v))
    return {"subjects": sorted(subjects)}


def check_a19_trigger(state: AgentState) -> str:
    return "emit_trace" if not state.subjects else "derive_target_response"


def _find_test(records: list[tuple[str, str, str]], testcd: str) -> tuple[str | None, str]:
    for visit, tc, val in records:
        if tc.upper() == testcd:
            return val, visit
    return None, ""


def derive_target_response(state: AgentState) -> dict:
    records = _rs_records(state.data_graph, state.subjects[0])
    resp, visit = _find_test(records, TARGET_TEST)
    return {"subjects": state.subjects[1:], "current_subject": state.subjects[0],
            "current_visit": visit, "target_response": resp}


def derive_nontarget_response(state: AgentState) -> dict:
    records = _rs_records(state.data_graph, state.current_subject)
    resp, _ = _find_test(records, NONTARGET_TEST)
    return {"nontarget_response": resp}


def derive_new_lesion_status(state: AgentState) -> dict:
    records = _rs_records(state.data_graph, state.current_subject)
    for _, tc, val in records:
        if tc.upper() == NEWLEC_TEST:
            return {"new_lesion_status": "YES" if val.upper() == "Y" else "NO"}
    return {"new_lesion_status": "YES" if _has_new_lesion(state.data_graph, state.current_subject) else "NO"}


def lookup_table7_node(state: AgentState) -> dict:
    if state.target_response and state.nontarget_response and state.new_lesion_status:
        expected = lookup_table7(state.target_response, state.nontarget_response, state.new_lesion_status)
    else:
        expected = None
    return {"expected_overall": expected}


def compare_overall(state: AgentState) -> dict:
    records = _rs_records(state.data_graph, state.current_subject)
    actual, _ = _find_test(records, TARGET_TEST)
    contradiction = bool(state.expected_overall and actual and state.expected_overall.upper() != actual.upper())
    return {"actual_overall": actual, "is_contradiction": contradiction}


def emit_trace(state: AgentState) -> dict:
    if not state.is_contradiction:
        return dict(_RESET)

    entry = create_trace_entry(
        subject=state.current_subject, visit=state.current_visit or None,
        layer="L3", archetype="A19", severity="violation", prev_hash="genesis",
        evidence_path=[
            {"type": k, "value": v} for k, v in [
                ("target_response", state.target_response),
                ("nontarget_response", state.nontarget_response),
                ("new_lesion_status", state.new_lesion_status),
                ("expected_overall", state.expected_overall),
                ("actual_overall", state.actual_overall),
            ]
        ],
        agent_trace={
            "agent": "CaveAgent", "archetype": "A19",
            "target": state.target_response, "nontarget": state.nontarget_response,
            "new_lesion": state.new_lesion_status,
            "expected": state.expected_overall, "actual": state.actual_overall,
        },
    )
    return {"traces": list(state.traces) + [entry.model_dump()], **_RESET}


# -- CaveAgent ------------------------------------------------------------------

class CaveAgent:
    """LangGraph agent for A19 (Table 7 overall response contradiction)."""

    def __init__(self, vendor_router: VendorRouter | None = None) -> None:
        self.router = vendor_router or VendorRouter()
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        g = StateGraph(AgentState)
        g.add_node("receive_l1_results", receive_l1_results)
        g.add_node("check_a19_trigger", lambda s: {})
        g.add_node("derive_target_response", derive_target_response)
        g.add_node("derive_nontarget_response", derive_nontarget_response)
        g.add_node("derive_new_lesion_status", derive_new_lesion_status)
        g.add_node("lookup_table7", lookup_table7_node)
        g.add_node("compare_overall", compare_overall)
        g.add_node("emit_trace", emit_trace)

        g.set_entry_point("receive_l1_results")
        g.add_edge("receive_l1_results", "check_a19_trigger")
        g.add_conditional_edges("check_a19_trigger", check_a19_trigger, {
            "derive_target_response": "derive_target_response",
            "emit_trace": "emit_trace",
        })
        g.add_edge("derive_target_response", "derive_nontarget_response")
        g.add_edge("derive_nontarget_response", "derive_new_lesion_status")
        g.add_edge("derive_new_lesion_status", "lookup_table7")
        g.add_edge("lookup_table7", "compare_overall")
        g.add_edge("compare_overall", "emit_trace")
        g.add_conditional_edges("emit_trace", lambda s: "check_a19_trigger" if s.subjects else END, {
            "check_a19_trigger": "check_a19_trigger", END: END,
        })
        return g.compile()

    def run(self, data_graph: Graph, l1_results: dict | None = None,
            prev_hash: str = "genesis") -> list[dict]:
        """Run A19 agent. Returns list of TraceEntry dicts for contradictions."""
        state = AgentState(data_graph=data_graph, l1_results=l1_results or {})
        result = self._graph.invoke(state)
        return result.get("traces", [])
