"""
G3: Scale benchmark -- measure CAVE-Onc L1 SHACL validation time at 1x, 5x, 10x subject counts.

Since the RECIST dataset has ~6 subjects, this script synthetically replicates
subjects with unique USUBJIDs to simulate larger datasets, then measures
L1 validation wall-clock time using the ShaclRunner.

Output: eval/g3_scale_benchmark.json

Usage:
    python -m scripts.run_scale_benchmark
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rdflib import Graph, Literal, URIRef, Namespace
from pyshacl import validate as shacl_validate


REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data" / "pharmaversesdtm_recist"
SHACL_DIR = REPO / "shacl"
OUT = REPO / "eval" / "g3_scale_benchmark.json"

CAVE = Namespace("https://cave-onc.org/shacl/")


def _load_data_graph(data_dir: Path) -> Graph:
    """Load XPT files into an RDF graph using the project's xpt_to_rdf adapter."""
    from kg.xpt_to_rdf import load_xpt_to_graph
    return load_xpt_to_graph(str(data_dir))


def _load_shapes_graph(shapes_dir: Path) -> Graph:
    """Load all .ttl shapes files."""
    g = Graph()
    for ttl in sorted(shapes_dir.glob("*.ttl")):
        g.parse(str(ttl), format="turtle")
    return g


def _count_subjects(graph: Graph) -> int:
    """Count unique USUBJIDs."""
    q = f"SELECT (COUNT(DISTINCT ?u) AS ?n) WHERE {{ ?s <{CAVE}USUBJID> ?u }}"
    results = list(graph.query(q))
    return int(results[0][0]) if results else 0


def _scale_graph(base_graph: Graph, scale_factor: int) -> Graph:
    """Create a scaled-up graph by replicating subjects with new USUBJIDs."""
    if scale_factor <= 1:
        return base_graph

    scaled = Graph()
    # Copy namespace bindings (required for SPARQL prefix resolution)
    for prefix, ns in base_graph.namespaces():
        scaled.bind(prefix, ns)

    # Copy all base triples
    for s, p, o in base_graph:
        scaled.add((s, p, o))

    for replica in range(1, scale_factor):
        suffix = f"_R{replica}"
        for s, p, o in base_graph:
            new_s = URIRef(str(s) + suffix)
            new_o = o
            if p == CAVE.USUBJID:
                new_o = Literal(str(o) + suffix)
            elif isinstance(o, URIRef):
                new_o = URIRef(str(o) + suffix)
            scaled.add((new_s, p, new_o))

    return scaled


def run_benchmark():
    """Run scale benchmark at 1x, 5x, 10x."""
    print("G3 Scale Benchmark")
    print("=" * 60)

    # Load base graph
    print(f"Loading base graph from {DATA_DIR}...")
    t0 = time.time()
    base_graph = _load_data_graph(DATA_DIR)
    load_time = time.time() - t0

    base_subjects = _count_subjects(base_graph)
    base_triples = len(base_graph)
    print(f"  Subjects: {base_subjects}")
    print(f"  Triples:  {base_triples:,}")
    print(f"  Load time: {load_time:.1f}s")

    # Load shapes
    shapes_graph = _load_shapes_graph(SHACL_DIR)
    n_shapes = len(list(shapes_graph.subjects()))
    print(f"  Shapes loaded from {SHACL_DIR}")

    results = {
        "benchmark": "G3_scale",
        "data_source": str(DATA_DIR),
        "base_subjects": base_subjects,
        "base_triples": base_triples,
        "base_load_time_s": round(load_time, 2),
        "scale_results": [],
    }

    # Run at each scale
    for factor, label in [(1, "1x"), (5, "5x"), (10, "10x")]:
        print(f"\n{'_' * 60}")
        print(f"Scale {label}: ~{base_subjects * factor} subjects (target)")

        t_scale = time.time()
        if factor == 1:
            graph = base_graph
        else:
            print(f"  Replicating graph {factor}x...")
            graph = _scale_graph(base_graph, factor)
        scale_time = time.time() - t_scale

        n_subjects = _count_subjects(graph)
        n_triples = len(graph)
        print(f"  Subjects: {n_subjects}")
        print(f"  Triples:  {n_triples:,}")

        print(f"  Running L1 SHACL validation...")
        t_val = time.time()
        try:
            conforms, report_graph, report_text = shacl_validate(
                graph,
                shacl_graph=shapes_graph,
                inference="none",
            )
            val_time = time.time() - t_val

            # Count violations
            if isinstance(report_graph, Graph):
                from rdflib.namespace import RDF
                SH = Namespace("http://www.w3.org/ns/shacl#")
                n_violations = len(list(report_graph.subjects(
                    RDF.type, SH.ValidationResult)))
            else:
                n_violations = -1

            print(f"  Validation: {val_time:.1f}s, {n_violations} violations, conforms={conforms}")
        except Exception as e:
            val_time = time.time() - t_val
            n_violations = -1
            print(f"  Validation ERROR after {val_time:.1f}s: {e}")

        entry = {
            "scale_factor": factor,
            "label": label,
            "subjects": n_subjects,
            "triples": n_triples,
            "scale_time_s": round(scale_time, 2),
            "validation_time_s": round(val_time, 2),
            "violations": n_violations,
            "time_per_subject_s": round(val_time / max(n_subjects, 1), 3),
        }
        results["scale_results"].append(entry)

    # Summary
    if len(results["scale_results"]) >= 2:
        t1 = results["scale_results"][0]["validation_time_s"]
        for entry in results["scale_results"]:
            entry["ratio_vs_1x"] = round(entry["validation_time_s"] / max(t1, 0.001), 2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Results saved to {OUT}")
    print("\nSummary:")
    for r in results["scale_results"]:
        print(f"  {r['label']:>3s}: {r['subjects']:>5d} subjects, "
              f"{r['triples']:>8,d} triples, "
              f"{r['validation_time_s']:>7.1f}s total, "
              f"{r['time_per_subject_s']:.3f}s/subj")


if __name__ == "__main__":
    run_benchmark()
