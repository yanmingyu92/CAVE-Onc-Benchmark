"""SHACL validation runner — validates an RDF graph against Trav-SHACL shapes.

For each violation/warning, emits a :class:`TraceEntry` (layer ``L1``)
to an :class:`AuditStore`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pyshacl import validate
from rdflib import Graph, Namespace, URIRef

try:
    from rdflib.namespace import RDF, SH
except ImportError:
    from rdflib import RDF, Namespace

    SH = Namespace("http://www.w3.org/ns/shacl#")

from audit.store import AuditStore
from audit.trace_schema import create_trace_entry
from shacl.shape_map import SHAPE_TO_ARCHETYPE

logger = logging.getLogger(__name__)

CDISC = Namespace("http://www.cdisc.org/ns/sdtm#")


def extract_usubjid(data_graph: Graph, focus: str) -> str:
    """Resolve USUBJID from the data graph, else parse the focus-node IRI.

    Shared by ShaclRunner (pyShACL path) and OxigraphSparqlRunner so both
    backends resolve subjects identically.
    """
    for obj in data_graph.objects(URIRef(focus), CDISC.USUBJID):
        return str(obj)
    parts = focus.rstrip("/").rsplit("/", 2)
    return parts[-2] if len(parts) >= 2 else ""


_SEVERITY_MAP: dict[str, str] = {
    str(SH.Violation): "violation",
    str(SH.Warning): "warning",
    str(SH.Info): "info",
}


class ShaclRunner:
    """Validates an RDF data graph against SHACL shapes and emits audit traces."""

    def __init__(
        self,
        data_graph: Graph,
        shapes_dir: str | Path = "shacl",
        shape_map: dict[str, tuple[str, list[str]]] | None = None,
        store: AuditStore | None = None,
        backend: Literal["pyshacl", "oxigraph"] = "pyshacl",
    ) -> None:
        self.data_graph = data_graph
        self.shapes_dir = Path(shapes_dir)
        self.shape_map = shape_map if shape_map is not None else SHAPE_TO_ARCHETYPE
        self.store = store
        self.backend = backend

    def run(self) -> dict[str, int]:
        """Run SHACL validation and emit TraceEntry records.

        Returns a summary dict with keys:
        ``conforms``, ``total``, ``violation``, ``warning``, ``info``.
        """
        if self.backend == "pyshacl":
            return self._validate_and_emit(self._load_shapes())
        if self.backend == "oxigraph":
            return self._run_oxigraph()
        raise ValueError(f"unknown backend: {self.backend!r}")

    def _run_oxigraph(self) -> dict[str, int]:
        """Hybrid backend: pyShACL over structural shapes + Oxigraph over SPARQL."""
        from shacl.oxigraph_runner import OxigraphSparqlRunner

        structural_files, _ = self._classify_shape_files()
        shapes_graph = Graph()
        for ttl in structural_files:
            shapes_graph.parse(str(ttl), format="turtle")
        counts = self._validate_and_emit(shapes_graph)

        ox_counts = OxigraphSparqlRunner(
            self.data_graph,
            shapes_dir=self.shapes_dir,
            shape_map=self.shape_map,
            store=self.store,
        ).run()
        for k in ("total", "violation", "warning", "info"):
            counts[k] += ox_counts[k]
        counts["conforms"] = 1 if counts["total"] == 0 else 0
        return counts

    def _classify_shape_files(self) -> tuple[list[Path], list[Path]]:
        """Split shape files into (structural, sparql) by presence of sh:sparql."""
        structural: list[Path] = []
        sparql: list[Path] = []
        for ttl in sorted(self.shapes_dir.glob("*.ttl")):
            text = ttl.read_text(encoding="utf-8")
            (sparql if "sh:sparql" in text else structural).append(ttl)
        return structural, sparql

    def _validate_and_emit(self, shapes_graph: Graph) -> dict[str, int]:
        """Run pyShACL with the given shapes graph and emit TraceEntry records."""
        conforms, report_graph, _ = validate(
            self.data_graph,
            shacl_graph=shapes_graph,
            inference="none",
        )

        # pyshacl may return a ValidationFailure instead of a Graph
        # when SPARQL constraints encounter execution errors
        if not isinstance(report_graph, Graph):
            logger.warning(
                "SHACL validation returned %s instead of Graph — "
                "possible SPARQL constraint error",
                type(report_graph).__name__,
            )
            return {
                "conforms": int(conforms),
                "total": 0,
                "violation": 0,
                "warning": 0,
                "info": 0,
            }

        violations = list(report_graph.subjects(RDF.type, SH.ValidationResult))
        counts: dict[str, int] = {
            "conforms": int(conforms),
            "total": 0,
            "violation": 0,
            "warning": 0,
            "info": 0,
        }

        prev_hash = "genesis"
        if self.store is not None:
            prev_hash = self.store.get_chain_tip()

        for vr in violations:
            severity = self._severity(vr, report_graph)
            shape_iri = self._str(vr, SH.sourceShape, report_graph)
            focus = self._str(vr, SH.focusNode, report_graph)
            usubjid = self._usubjid(focus)
            archetype_id, core_xref = self.shape_map.get(
                shape_iri,
                (self._default_archetype(shape_iri), [shape_iri]),
            )

            entry = create_trace_entry(
                subject=usubjid or focus,
                layer="L1",
                archetype=archetype_id,
                severity=severity,
                prev_hash=prev_hash,
                shacl_shape=shape_iri,
                evidence_path=self._evidence(vr, report_graph),
                core_rule_xref=core_xref,
            )

            if self.store is not None:
                self.store.append(entry)

            prev_hash = entry.entry_hash
            counts[severity] += 1
            counts["total"] += 1

        logger.info(
            "SHACL validation complete: conforms=%s, violations=%d",
            conforms,
            counts["total"],
        )
        return counts

    # -- helpers ---------------------------------------------------------------

    def _load_shapes(self) -> Graph:
        """Load all ``.ttl`` files from the shapes directory."""
        g = Graph()
        for ttl in sorted(self.shapes_dir.glob("*.ttl")):
            g.parse(str(ttl), format="turtle")
        return g

    def _severity(self, vr: URIRef, rg: Graph) -> str:
        sev = self._first(vr, SH.resultSeverity, rg)
        return _SEVERITY_MAP.get(str(sev), "violation") if sev else "violation"

    def _usubjid(self, focus: str) -> str:
        """Extract USUBJID from the data graph or from the focus-node IRI."""
        return extract_usubjid(self.data_graph, focus)

    def _default_archetype(self, shape_iri: str) -> str:
        if "/" in shape_iri:
            return shape_iri.rsplit("/", 1)[1].replace("Shape_", "")
        return shape_iri

    def _evidence(self, vr: URIRef, rg: Graph) -> list[dict]:
        out: list[dict] = []
        for msg in rg.objects(vr, SH.resultMessage):
            out.append({"type": "resultMessage", "value": str(msg)})
        path = self._first(vr, SH.resultPath, rg)
        if path is not None:
            out.append({"type": "resultPath", "value": str(path)})
        val = self._first(vr, SH.value, rg)
        if val is not None:
            out.append({"type": "value", "value": str(val)})
        return out

    @staticmethod
    def _first(subject, predicate, graph):
        for obj in graph.objects(subject, predicate):
            return obj
        return None

    def _str(self, subject, predicate, graph) -> str:
        v = self._first(subject, predicate, graph)
        return str(v) if v is not None else ""
