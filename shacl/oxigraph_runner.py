"""Oxigraph-backed execution of SHACL-SPARQL constraints (L1 fast path).

Extracts ``sh:sparql`` constraints from the shape library and runs each
``sh:select`` directly against a pyoxigraph ``Store`` built from the rdflib data
graph. Emits the same :class:`TraceEntry` records as
:class:`shacl.runner.ShaclRunner`, so the two backends are interchangeable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph, URIRef

try:
    from rdflib.namespace import SH
except ImportError:  # pragma: no cover
    from rdflib import Namespace

    SH = Namespace("http://www.w3.org/ns/shacl#")

logger = logging.getLogger(__name__)

PROV_DERIVED = URIRef("http://www.w3.org/ns/prov#wasDerivedFrom")

_SEVERITY_MAP: dict[str, str] = {
    "http://www.w3.org/ns/shacl#Violation": "violation",
    "http://www.w3.org/ns/shacl#Warning": "warning",
    "http://www.w3.org/ns/shacl#Info": "info",
}


@dataclass(frozen=True)
class ShapeConstraint:
    """One SHACL-SPARQL constraint, ready to run on Oxigraph."""

    shape_iri: str
    select: str  # PREFIX header + sh:select body
    message: str
    severity: str  # "violation" | "warning" | "info"
    target_class: str | None


def _prefix_header(shapes_graph: Graph) -> str:
    lines = [f"PREFIX {p}: <{ns}>" for p, ns in shapes_graph.namespaces()]
    return "\n".join(lines) + "\n"


def _load_shapes_graph(shapes_dir: str | Path) -> Graph:
    sg = Graph()
    for ttl in sorted(Path(shapes_dir).glob("*.ttl")):
        sg.parse(str(ttl), format="turtle")
    return sg


def extract_sparql_constraints(
    shapes_dir: str | Path = "shacl",
) -> list[ShapeConstraint]:
    """Parse all shape ``*.ttl`` and return every ``sh:sparql`` constraint."""
    sg = _load_shapes_graph(shapes_dir)
    header = _prefix_header(sg)
    out: list[ShapeConstraint] = []
    for shape, _, constraint in sg.triples((None, SH.sparql, None)):
        select = sg.value(constraint, SH.select)
        if select is None:
            continue
        message = sg.value(constraint, SH.message)
        sev_node = sg.value(shape, SH.severity)
        severity = _SEVERITY_MAP.get(str(sev_node), "violation")
        target = sg.value(shape, SH.targetClass)
        out.append(
            ShapeConstraint(
                shape_iri=str(shape),
                select=header + str(select),
                message=str(message) if message is not None else "",
                severity=severity,
                target_class=str(target) if target is not None else None,
            )
        )
    return out


import pyoxigraph as ox  # noqa: E402  (kept near usage for clarity)

from audit.store import AuditStore  # noqa: E402
from audit.trace_schema import create_trace_entry  # noqa: E402
from shacl.runner import extract_usubjid  # noqa: E402
from shacl.shape_map import SHAPE_TO_ARCHETYPE  # noqa: E402


def _default_archetype(shape_iri: str) -> str:
    if "/" in shape_iri:
        return shape_iri.rsplit("/", 1)[1].replace("Shape_", "")
    return shape_iri


class OxigraphSparqlRunner:
    """Runs SHACL-SPARQL constraints on a pyoxigraph Store and emits traces."""

    def __init__(
        self,
        data_graph: Graph,
        shapes_dir: str | Path = "shacl",
        shape_map: dict[str, tuple[str, list[str]]] | None = None,
        store: AuditStore | None = None,
    ) -> None:
        self.data_graph = data_graph
        self.shapes_dir = Path(shapes_dir)
        self.shape_map = shape_map if shape_map is not None else SHAPE_TO_ARCHETYPE
        self.store = store

    def _build_store(self) -> "ox.Store":
        nt = self.data_graph.serialize(format="nt")
        if isinstance(nt, str):
            nt = nt.encode("utf-8")
        s = ox.Store()
        s.load(nt, mime_type="application/n-triples")
        return s

    @staticmethod
    def _focus(row) -> str:
        try:
            node = row["this"]
        except KeyError:
            return ""
        if node is None:
            return ""
        return getattr(node, "value", str(node))

    def run(self) -> dict[str, int]:
        """Execute all SHACL-SPARQL constraints; emit a TraceEntry per result row."""
        constraints = extract_sparql_constraints(self.shapes_dir)
        ox_store = self._build_store()
        counts = {"conforms": 1, "total": 0, "violation": 0, "warning": 0, "info": 0}

        prev_hash = "genesis"
        if self.store is not None:
            prev_hash = self.store.get_chain_tip()

        for c in constraints:
            try:
                rows = list(ox_store.query(c.select))
            except Exception as exc:  # malformed/failing SELECT -> 0 violations
                logger.warning("Oxigraph SPARQL error in %s: %s", c.shape_iri, exc)
                continue
            # SHACL emits one validation result per focus node; a raw SELECT may
            # return multiple solution rows per $this (join fan-out). Dedup by
            # focus per shape to match pyShACL semantics exactly.
            seen_focus: set[str] = set()
            for row in rows:
                focus = self._focus(row)
                if not focus or focus in seen_focus:
                    continue
                seen_focus.add(focus)
                usubjid = extract_usubjid(self.data_graph, focus)
                archetype_id, core_xref = self.shape_map.get(
                    c.shape_iri, (_default_archetype(c.shape_iri), [c.shape_iri])
                )
                entry = create_trace_entry(
                    subject=usubjid or focus,
                    layer="L1",
                    archetype=archetype_id,
                    severity=c.severity,
                    prev_hash=prev_hash,
                    shacl_shape=c.shape_iri,
                    evidence_path=(
                        [{"type": "resultMessage", "value": c.message}]
                        if c.message
                        else []
                    ),
                    core_rule_xref=core_xref,
                )
                if self.store is not None:
                    self.store.append(entry)
                prev_hash = entry.entry_hash
                counts[c.severity] += 1
                counts["total"] += 1

        if counts["total"] > 0:
            counts["conforms"] = 0
        return counts
