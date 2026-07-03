"""B_CAVE full pipeline — L1 SHACL + L3 agent (A19 Table 7 contradiction).

Fully functional — uses kg/xpt_to_rdf.py + shacl/runner.py + agent/orchestrator.py.
No external deps beyond pyshacl + rdflib + langgraph (already installed).
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent.orchestrator import CaveAgent
from audit.store import AuditStore, _row_to_entry
from kg.xpt_to_rdf import load_xpt_to_graph
from shacl.runner import ShaclRunner

from eval.flag_schema import FlagRecord, FlagSet

logger = logging.getLogger(__name__)

_AGENT_DOMAIN_MAP = {
    "A19": "RS",
}


def _extract_domain(subject: str, archetype: str | None) -> str:
    if archetype and archetype in _AGENT_DOMAIN_MAP:
        return _AGENT_DOMAIN_MAP[archetype]
    import re
    m = re.search(r"/(DM|EX|TU|TR|RS)/", subject, re.IGNORECASE)
    return m.group(1).upper() if m else "unknown"


def _trace_to_flag(entry_dict: dict, source: str) -> FlagRecord:
    return FlagRecord(
        subject=entry_dict.get("subject", ""),
        archetype=entry_dict.get("archetype"),
        rule_id=entry_dict.get("shacl_shape") or (
            entry_dict.get("core_rule_xref", ["unknown"])[0]
            if entry_dict.get("core_rule_xref") else "A19_TABLE7"
        ),
        domain=_extract_domain(
            entry_dict.get("subject", ""),
            entry_dict.get("archetype"),
        ),
        severity=entry_dict.get("severity", "violation"),
        message=_build_message(entry_dict),
        source=source,
    )


def _build_message(entry_dict: dict) -> str:
    ep = entry_dict.get("evidence_path") or []
    parts = [e.get("value", "") for e in ep if e.get("value")]
    at = entry_dict.get("agent_trace")
    if at:
        parts.append(f"expected={at.get('expected')}, actual={at.get('actual')}")
    return "; ".join(parts) if parts else entry_dict.get("severity", "violation")


def _l1_flags(data_dir: Path) -> list[FlagRecord]:
    """Run L1 SHACL and convert to FlagRecords with source CAVE."""
    graph = load_xpt_to_graph(data_dir)
    flags: list[FlagRecord] = []
    with AuditStore(":memory:") as store:
        runner = ShaclRunner(graph, store=store)
        runner.run()
        cur = store._conn.execute("SELECT * FROM traces ORDER BY rowid ASC")
        rows = cur.fetchall()
    for row in rows:
        entry = _row_to_entry(row)
        flags.append(_trace_to_flag(entry.model_dump(), "CAVE"))
    return flags


def _l3_flags(data_dir: Path) -> list[FlagRecord]:
    """Run L3 CaveAgent (A19) and convert to FlagRecords with source CAVE."""
    graph = load_xpt_to_graph(data_dir)
    agent = CaveAgent()
    traces = agent.run(graph)
    flags: list[FlagRecord] = []
    for t in traces:
        flags.append(_trace_to_flag(t, "CAVE"))
    return flags


def run(data_dir: Path) -> FlagSet:
    """Full CAVE pipeline: L1 SHACL + L3 agent. Returns merged FlagSet."""
    l1 = _l1_flags(data_dir)
    l3 = _l3_flags(data_dir)
    all_flags = l1 + l3
    logger.info("B_CAVE: %d flags (L1=%d, L3=%d) from %s",
                len(all_flags), len(l1), len(l3), data_dir)
    return FlagSet(all_flags)
