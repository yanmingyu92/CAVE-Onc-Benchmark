"""B3 L1-only baseline — loads XPTs, runs SHACL validation, returns FlagRecords.

Fully functional — uses kg/xpt_to_rdf.py + shacl/runner.py.
No external deps beyond pyshacl + rdflib (already installed).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from audit.store import AuditStore
from audit.trace_schema import TraceEntry
from kg.xpt_to_rdf import load_xpt_to_graph
from shacl.runner import ShaclRunner

from eval.flag_schema import FlagRecord, FlagSet

logger = logging.getLogger(__name__)

_DOMAIN_RE = re.compile(r"/(DM|EX|TU|TR|RS)/", re.IGNORECASE)


def _extract_domain(entry: TraceEntry) -> str:
    """Extract domain from the shape IRI or evidence."""
    # Try shape IRI: e.g. "https://cave-onc.org/shacl/Shape_CORE-000068" → need xref
    # Try evidence_path for focus node domain
    for ev in entry.evidence_path:
        v = ev.get("value", "")
        m = _DOMAIN_RE.search(v)
        if m:
            return m.group(1).upper()
    # Fallback: infer from archetype naming or shape
    shape = entry.shacl_shape or ""
    if shape:
        # Shapes are per-domain in their .ttl files; map from xref_table
        # For now, use "DM" as default since most shapes are DM-scoped
        pass
    return "unknown"


def _trace_to_flag(entry: TraceEntry) -> FlagRecord:
    # Prefer core_rule_xref for rule_id — matches CORE format for Jaccard
    if entry.core_rule_xref:
        rule_id = entry.core_rule_xref[0]
    elif entry.shacl_shape:
        rule_id = entry.shacl_shape
    else:
        rule_id = "unknown"
    msg_parts = [e.get("value", "") for e in entry.evidence_path if e.get("value")]
    return FlagRecord(
        subject=entry.subject,
        archetype=entry.archetype,
        rule_id=rule_id,
        domain=_extract_domain(entry),
        severity=entry.severity,
        message="; ".join(msg_parts) if msg_parts else entry.severity,
        source="B3_L1",
    )


def run(data_dir: Path) -> FlagSet:
    """Load XPTs from *data_dir*, run SHACL L1 validation, return FlagSet."""
    graph = load_xpt_to_graph(data_dir)
    flags: list[FlagRecord] = []

    with AuditStore(":memory:") as store:
        runner = ShaclRunner(graph, store=store)
        runner.run()
        cur = store._conn.execute("SELECT * FROM traces ORDER BY rowid ASC")
        rows = cur.fetchall()

    # _row_to_entry is module-level in audit.store
    from audit.store import _row_to_entry
    for row in rows:
        entry = _row_to_entry(row)
        flags.append(_trace_to_flag(entry))

    logger.info("B3 L1: %d flags from %s", len(flags), data_dir)
    return FlagSet(flags)
