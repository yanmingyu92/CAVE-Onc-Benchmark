"""Gate 2b (efficiency) — large-scale Oxigraph detection benchmark.

Turns the "~2-minute weakness" into a measured strength. The manuscript's G3
micro-benchmark scaled the reference pyShACL stack to ~60 subjects; this measures
the deployable **Oxigraph** detection backend at **1k / 2k / 5k synthetic
subjects** and reports wall-clock, throughput (subjects/sec), peak process memory,
and the sub-linearity of the scaling curve.

Synthetic cohorts are built by replicating the real benchmark cohort (pilot1,
254 subjects, full TU/TR/RS/DM/DS/AE/EX topology) with fresh USUBJIDs, so every
replicated subject carries a realistic cross-domain structure. Because the
archetype SHACL-SPARQL shapes are USUBJID-scoped joins, this is a faithful load
model. The `OxigraphSparqlRunner` (the L1 cross-domain detection component) is
measured directly; the pyShACL structural step (the remaining rdflib-only cost)
is measured once and reported separately.

Reproducible; peak memory via psutil RSS sampling.

Usage:
    python -m scripts.run_scale_benchmark_large --targets 1000 2000 5000 \
        --out eval/scale_benchmark_large.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import threading
import time
from pathlib import Path

import psutil
from rdflib import Graph, Literal, URIRef

from audit.store import AuditStore
from bench.injector import Injector
from kg.ontology import CAVE
from scripts.track_b_analysis import _frames_to_graph
from shacl.oxigraph_runner import OxigraphSparqlRunner
from shacl.runner import ShaclRunner

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_PROC = psutil.Process()


def _rss_mb() -> float:
    return _PROC.memory_info().rss / (1024 * 1024)


class _PeakRSS:
    """Background sampler for the true process RSS high-water mark.

    Point-sampling around a synchronous call misses the transient peak *inside*
    it (e.g. the N-Triples serialisation buffer resident alongside the rdflib
    graph and the Oxigraph store). A polling thread catches it.
    """

    def __init__(self, interval_s: float = 0.05) -> None:
        self._interval = interval_s
        self._peak = _rss_mb()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._peak = max(self._peak, _rss_mb())
            self._stop.wait(self._interval)

    def __enter__(self) -> "_PeakRSS":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._peak = max(self._peak, _rss_mb())

    @property
    def peak_mb(self) -> float:
        return self._peak


def _count_subjects(g: Graph) -> int:
    q = f"SELECT (COUNT(DISTINCT ?u) AS ?n) WHERE {{ ?s <{CAVE}USUBJID> ?u }}"
    rows = list(g.query(q))
    return int(rows[0][0]) if rows else 0


def loglog_slope(results: list[dict], key: str) -> tuple[float | None, float | None]:
    """Least-squares log-log slope (power-law exponent) + R^2 of ``key`` vs subjects.

    Fits over ALL sweep points, not just the two endpoints, so a single noisy run
    cannot flip the exponent. Returns (slope, r2) rounded, or (None, None).
    """
    pts = [(r["subjects"], r[key]) for r in results
           if r.get("subjects", 0) > 0 and r.get(key, 0) > 1e-6]
    if len(pts) < 2:
        return None, None
    xs = [math.log(s) for s, _ in pts]
    ys = [math.log(t) for _, t in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None, None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return round(slope, 3), round(r2, 4)


def _replicate(base: Graph, factor: int) -> Graph:
    """Replicate the base graph `factor` times with distinct subject IRIs/USUBJIDs."""
    if factor <= 1:
        return base
    scaled = Graph()
    for prefix, ns in base.namespaces():
        scaled.bind(prefix, ns)
    for t in base:
        scaled.add(t)
    for r in range(1, factor):
        suffix = f"_R{r}"
        for s, p, o in base:
            ns = URIRef(str(s) + suffix) if isinstance(s, URIRef) else s
            # Suffix any USUBJID literal (both cave: and cdisc: predicates the graph
            # builder emits) so replicas are truly distinct subjects on every axis.
            if str(p).endswith("USUBJID"):
                no = Literal(str(o) + suffix)
            elif isinstance(o, URIRef):
                no = URIRef(str(o) + suffix)
            else:
                no = o
            scaled.add((ns, p, no))
    return scaled


def _measure_oxigraph(graph: Graph) -> dict:
    """Measure store-build vs SPARQL-query time separately for the detection step.

    Returns load_s (rdflib->oxigraph store build), query_s (the actual SHACL-SPARQL
    detection), total flags, and peak process RSS (MB). Separating them isolates the
    detection-algorithm scaling from the one-time graph-materialisation cost.
    """
    from shacl.oxigraph_runner import extract_sparql_constraints

    runner = OxigraphSparqlRunner(graph, shapes_dir="shacl")
    with _PeakRSS() as peak:  # catches the serialisation-buffer transient
        t = time.time()
        ox_store = runner._build_store()
        load_s = time.time() - t

        constraints = extract_sparql_constraints("shacl")
        t = time.time()
        total = 0
        for c in constraints:
            try:
                rows = list(ox_store.query(c.select))
            except Exception:  # noqa: BLE001 — mirror runner's tolerant behaviour
                continue
            seen: set[str] = set()
            for row in rows:
                focus = runner._focus(row)
                if focus and focus not in seen:
                    seen.add(focus)
                    total += 1
        query_s = time.time() - t
    return {"load_s": load_s, "query_s": query_s, "flags": total,
            "peak_mb": peak.peak_mb}


def run(targets: list[int], out: Path, structural_at: int = 1000) -> dict:
    t0 = time.time()
    base_frames = Injector(output_dir="bench/output_scale_large")._load_all()
    base_graph = _frames_to_graph(base_frames)
    base_subjects = _count_subjects(base_graph)
    logger.info("base cohort: %d subjects, %d triples", base_subjects, len(base_graph))

    results: list[dict] = []
    for target in targets:
        factor = max(1, round(target / max(base_subjects, 1)))
        t_build = time.time()
        graph = _replicate(base_graph, factor)
        build_s = time.time() - t_build
        n_subj = _count_subjects(graph)
        n_trip = len(graph)
        m = _measure_oxigraph(graph)
        det_s = m["load_s"] + m["query_s"]
        entry = {
            "target_subjects": target, "replication_factor": factor,
            "subjects": n_subj, "triples": n_trip,
            "graph_build_s": round(build_s, 2),
            "store_load_s": round(m["load_s"], 2),
            "sparql_query_s": round(m["query_s"], 2),
            "oxigraph_detect_s": round(det_s, 2),
            "archetype_flags": m["flags"],
            "query_throughput_subjects_per_s": round(n_subj / max(m["query_s"], 1e-6), 1),
            "end_to_end_throughput_subjects_per_s": round(n_subj / max(det_s, 1e-6), 1),
            "query_ms_per_subject": round(m["query_s"] * 1000 / max(n_subj, 1), 3),
            "peak_rss_mb": round(m["peak_mb"], 1),
        }
        results.append(entry)
        logger.info("%d subj: load %.1fs + query %.1fs, %.0f subj/s (query), %.0f MB peak",
                    n_subj, m["load_s"], m["query_s"],
                    entry["query_throughput_subjects_per_s"], m["peak_mb"])

    # Scaling: least-squares log-log slope of time vs subjects over ALL sweep points.
    query_exp, query_r2 = loglog_slope(results, "sparql_query_s")
    e2e_exp, e2e_r2 = loglog_slope(results, "oxigraph_detect_s")
    scaling_exponent = query_exp
    sublinear = bool(query_exp is not None and query_exp < 1.0)

    # Remaining rdflib-only structural step cost (measured once).
    structural = None
    factor = max(1, round(structural_at / max(base_subjects, 1)))
    sgraph = _replicate(base_graph, factor)
    t = time.time()
    try:
        structural_files, _ = ShaclRunner(sgraph)._classify_shape_files()
        shapes_graph = Graph()
        for ttl in structural_files:
            shapes_graph.parse(str(ttl), format="turtle")
        with AuditStore(":memory:") as store:
            ShaclRunner(sgraph, store=store)._validate_and_emit(shapes_graph)
        structural = {
            "subjects": _count_subjects(sgraph),
            "structural_pyshacl_s": round(time.time() - t, 2),
            "note": "rdflib/pyShACL structural (RECIST S1-S8 + domain) step — the "
                    "remaining non-Oxigraph cost; scales with the reference stack.",
        }
    except Exception as exc:  # noqa: BLE001
        structural = {"error": str(exc)}

    report = {
        "benchmark": "scale_large_oxigraph",
        "base_subjects": base_subjects,
        "base_triples": len(base_graph),
        "scale_results": results,
        "scaling": {
            "sparql_query_exponent_loglog": query_exp,
            "sparql_query_fit_r2": query_r2,
            "end_to_end_exponent_loglog": e2e_exp,
            "end_to_end_fit_r2": e2e_r2,
            "detection_scaling_exponent_loglog": scaling_exponent,
            "sub_linear": sublinear,
            "fit_method": "least_squares_loglog_over_all_points",
            "interpretation": (
                "least-squares log-log slope of SPARQL detection time vs subject "
                "count over all sweep points; <1 sub-linear, ~1 linear, >1 "
                "super-linear. store_load (rdflib->oxigraph materialisation) is a "
                "separate one-time cost."),
        },
        "structural_step": structural,
        "runtime_sec": round(time.time() - t0, 1),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"scale_results": results, "scaling": report["scaling"],
                      "structural_step": structural}, indent=2))
    print("->", out)
    return report


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Large-scale Oxigraph detection benchmark.")
    ap.add_argument("--targets", type=int, nargs="+", default=[1000, 2000, 5000])
    ap.add_argument("--out", default="eval/scale_benchmark_large.json")
    ap.add_argument("--structural-at", type=int, default=1000)
    a = ap.parse_args(argv)
    run(a.targets, Path(a.out), a.structural_at)


if __name__ == "__main__":
    main()
