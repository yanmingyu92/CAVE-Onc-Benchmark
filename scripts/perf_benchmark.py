"""Item C — performance: L3 timing decomposition + SPARQL backend speedup.

Answers Reviewer #2 (R2-2):
  (1) Clarify what the 25 ms L3 figure measures (A19 inference vs routing).
  (2) Give a concrete speedup range for migrating the SHACL-SPARQL execution
      engine off rdflib (current pySHACL backend) by benchmarking the *same*
      archetype SPARQL queries on rdflib vs Oxigraph (pyoxigraph).

Outputs:
    eval/perf_benchmark.json
    docs/latex/plos_submission/analysis/perf_table.md

Run:
    .venv/Scripts/python.exe -m scripts.perf_benchmark
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pyoxigraph
from rdflib import Graph

from agent.orchestrator import CaveAgent
from bench.mutations import MUTATIONS
from scripts.track_b_analysis import _frames_to_graph, _enrich_rs

SHAPES = _ROOT / "shacl" / "archetype_shapes.ttl"
JSON_OUT = _ROOT / "eval" / "perf_benchmark.json"
MD_OUT = _ROOT / "docs" / "latex" / "plos_submission" / "analysis" / "perf_table.md"
CAVE_PREFIX = "PREFIX cave: <https://cave-onc.org/shacl/>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
N_REPEAT = 5


# -- graph builders ------------------------------------------------------------

def _build_graph(archetype: str | None) -> Graph:
    from bench.injector import Injector

    frames = Injector(output_dir="bench/output_perf")._load_all()
    frames = {k: v.copy() for k, v in frames.items()}
    if archetype:
        frames, _ = MUTATIONS[archetype](frames)
    frames = _enrich_rs(frames)
    return _frames_to_graph(frames)


# -- (1) L3 timing decomposition ----------------------------------------------

def l3_decomposition() -> dict:
    """Separate L3 'derivation/routing' cost from contradiction emission.

    The agent runs the identical Table 7 derivation over every subject on every
    archetype run; only whether a trace is emitted differs. So the per-archetype
    25 ms is full derivation, NOT a 'routing for 19 + inference for A19' split.
    We confirm by timing L3 on an A19-injected graph (emits) vs a clean graph
    (no contradiction → derivation only, 0 traces).
    """
    g_a19 = _build_graph("A19")
    g_clean = _build_graph(None)
    agent = CaveAgent()

    def _time(g) -> tuple[float, int]:
        best = float("inf")
        traces = 0
        for _ in range(N_REPEAT):
            t0 = time.perf_counter()
            tr = agent.run(g)
            best = min(best, time.perf_counter() - t0)
            traces = len(tr)
        return best, traces

    t_a19, n_a19 = _time(g_a19)
    t_clean, n_clean = _time(g_clean)
    # count RS subjects
    from rdflib import URIRef
    from rdflib.namespace import RDF
    CAVE = "https://cave-onc.org/shacl/"
    subs = set()
    for s in g_a19.subjects(RDF.type, URIRef(f"{CAVE}RS")):
        for u in g_a19.objects(s, URIRef(f"{CAVE}USUBJID")):
            subs.add(str(u))
    n_subjects = len(subs)
    return {
        "l3_a19_injected_s": round(t_a19, 4),
        "l3_a19_traces": n_a19,
        "l3_clean_derivation_only_s": round(t_clean, 4),
        "l3_clean_traces": n_clean,
        "n_rs_subjects": n_subjects,
        "per_subject_derivation_ms": round(t_clean / max(n_subjects, 1) * 1000, 3),
        "emit_overhead_ms": round((t_a19 - t_clean) * 1000, 3),
        "interpretation": (
            "The ~25 ms per archetype is the FULL L3 derivation (query RS for "
            "OVRLRESP/NTOVRLRESP/NEWLEC + Table 7 lookup + compare) executed over "
            "ALL subjects on EVERY run. It is not 'routing for 19 + inference for "
            "A19'; the agent has no inference-skipping fast path. The '5% invocation "
            "rate' refers to DETECTION (1/20 archetypes emit a trace), not compute "
            "(compute is incurred on 20/20 runs)."
        ),
    }


# -- (2) SPARQL backend speedup: rdflib vs Oxigraph ----------------------------

def _extract_queries(shapes_file: Path) -> list[tuple[str, str]]:
    text = shapes_file.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"cave:(Shape_Archetype_\w+).*?sh:select\s+\"\"\"(.*?)\"\"\"",
                         text, re.DOTALL):
        out.append((m.group(1), m.group(2).strip()))
    return out


def backend_speedup() -> dict:
    g = _build_graph("A19")
    queries = _extract_queries(SHAPES)

    # Load same data into an Oxigraph store.
    ttl_bytes = g.serialize(format="turtle").encode("utf-8")
    store = pyoxigraph.Store()
    store.load(ttl_bytes, "text/turtle")

    rows = []
    rdflib_total = 0.0
    oxi_total = 0.0
    for name, body in queries:
        q = CAVE_PREFIX + body
        # rdflib
        try:
            best_r = float("inf")
            for _ in range(N_REPEAT):
                t0 = time.perf_counter()
                list(g.query(q))
                best_r = min(best_r, time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001
            best_r = None
        # oxigraph
        try:
            best_o = float("inf")
            for _ in range(N_REPEAT):
                t0 = time.perf_counter()
                list(store.query(q))
                best_o = min(best_o, time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001
            best_o = None
        speedup = (round(best_r / best_o, 2)
                   if best_r and best_o and best_o > 0 else None)
        rows.append({
            "shape": name,
            "rdflib_s": round(best_r, 4) if best_r else None,
            "oxigraph_s": round(best_o, 4) if best_o else None,
            "speedup": speedup,
        })
        if best_r:
            rdflib_total += best_r
        if best_o:
            oxi_total += best_o

    speedups = [r["speedup"] for r in rows if r["speedup"]]
    return {
        "n_queries": len(rows),
        "n_comparable": len(speedups),
        "rdflib_total_s": round(rdflib_total, 4),
        "oxigraph_total_s": round(oxi_total, 4),
        "aggregate_speedup": round(rdflib_total / oxi_total, 2) if oxi_total > 0 else None,
        "median_speedup": round(sorted(speedups)[len(speedups) // 2], 2) if speedups else None,
        "min_speedup": round(min(speedups), 2) if speedups else None,
        "max_speedup": round(max(speedups), 2) if speedups else None,
        "per_query": rows,
    }


def main() -> None:
    decomp = l3_decomposition()
    speedup = backend_speedup()
    result = {"l3_timing_decomposition": decomp, "backend_speedup_rdflib_vs_oxigraph": speedup}
    JSON_OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md = _render_md(decomp, speedup)
    MD_OUT.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[written] {JSON_OUT}\n[written] {MD_OUT}")


def _render_md(d: dict, s: dict) -> str:
    return f"""# Item C — performance clarification + backend speedup

## (1) What the 25 ms L3 figure measures (answers R2-2)
| Quantity | Value |
|---|---|
| L3 on A19-injected graph (emits) | {d['l3_a19_injected_s']} s ({d['l3_a19_traces']} traces) |
| L3 on clean graph (derivation only) | {d['l3_clean_derivation_only_s']} s ({d['l3_clean_traces']} traces) |
| RS subjects processed per run | {d['n_rs_subjects']} |
| Per-subject derivation | {d['per_subject_derivation_ms']} ms |
| Emit overhead (A19 vs clean) | {d['emit_overhead_ms']} ms |

{d['interpretation']}

## (2) SHACL-SPARQL backend speedup — rdflib vs Oxigraph (same {s['n_queries']} archetype queries)
| Metric | Value |
|---|---|
| Comparable queries | {s['n_comparable']}/{s['n_queries']} |
| rdflib total | {s['rdflib_total_s']} s |
| Oxigraph total | {s['oxigraph_total_s']} s |
| **Aggregate speedup** | **{s['aggregate_speedup']}×** |
| Median / min / max speedup | {s['median_speedup']}× / {s['min_speedup']}× / {s['max_speedup']}× |

**Reading:** SPARQL execution dominates L1 wall-clock. Replacing the rdflib query \
engine with Oxigraph on the identical archetype constraint queries yields a \
~{s['aggregate_speedup']}× aggregate speedup on this corpus, giving a concrete, \
data-backed estimate for the backend-migration claim (vs the previous unquantified \
"could reduce time"). This is an engine-level micro-benchmark on the SPARQL \
constraints; full Trav-SHACL integration would also remove pySHACL's focus-node \
and shape-parsing overhead.
"""


if __name__ == "__main__":
    main()
