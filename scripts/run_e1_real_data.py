"""E1 naturalistic run: validate UNMUTATED mapped real SDTM against the full
shape library, aggregate flags per shape, for specificity assessment.

See docs/item_e_real_data_plan.md (Phase 2). Output: eval/real_data_e1_<tag>.json
"""
from __future__ import annotations
import argparse, json, time
from collections import Counter
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH
from pyshacl import validate

from kg.xpt_to_rdf import load_xpt_to_graph
from kg.ontology import CAVE
from scripts.map_synta_to_sdtm import enrich_recist_graph


def _subset(g: Graph, max_subjects: int) -> Graph:
    """Keep only triples for the first N USUBJIDs (by sorted order)."""
    subs = sorted({str(o) for _, o in g.subject_objects(CAVE["USUBJID"])})[:max_subjects]
    keep = set(subs)
    out = Graph()
    # Preserve namespace bindings — pyshacl resolves SPARQL prefixes (cave:, cdisc:)
    # from the DATA graph's namespace_manager, so a fresh Graph must re-bind them.
    for prefix, ns in g.namespaces():
        out.bind(prefix, ns)
    for s, p, o in g:
        # subject IRIs encode usubjid as cave:<dom>/<usubjid>/<seq>
        uid = str(s).rstrip("/").rsplit("/", 2)
        # Keep subject-scoped triples for kept USUBJIDs, AND always keep
        # trial-design domains (TA/TE/etc.) which use the '_trial_' placeholder
        # and variable/label annotation triples (not '/'-segmented record IRIs).
        if len(uid) >= 2 and (uid[-2] in keep or uid[-2] == "_trial_"):
            out.add((s, p, o))
        elif len(uid) < 2 or not uid[-1].isdigit():
            out.add((s, p, o))
    return out


def _validate(g: Graph, backend: str):
    """Validate g with the chosen backend; return (conforms, per_shape, per_subject, ok).

    backend="oxigraph" routes the SHACL-SPARQL detectors through pyoxigraph (avoiding
    the rdflib GROUP BY blowup) and keeps pyShACL for structural shapes; counters are
    rebuilt from the audit traces so downstream bucketing is backend-agnostic.
    """
    per_shape: Counter = Counter()
    per_subject: Counter = Counter()
    if backend == "pyshacl":
        shapes = Graph()
        for ttl in sorted(Path("shacl").glob("*.ttl")):
            shapes.parse(str(ttl), format="turtle")
        conforms, report, _ = validate(g, shacl_graph=shapes, inference="none")
        if not isinstance(report, Graph):
            return bool(conforms), per_shape, per_subject, False
        for vr in report.subjects(RDF.type, SH.ValidationResult):
            shp = next(report.objects(vr, SH.sourceShape), None)
            focus = next(report.objects(vr, SH.focusNode), None)
            per_shape[str(shp).rsplit("/", 1)[-1] if shp else "?"] += 1
            if focus is not None:
                uid = str(focus).rstrip("/").rsplit("/", 2)
                per_subject[uid[-2] if len(uid) >= 2 else str(focus)] += 1
        return bool(conforms), per_shape, per_subject, True

    # oxigraph hybrid backend
    from audit.store import AuditStore, _row_to_entry
    from shacl.runner import ShaclRunner

    with AuditStore(":memory:") as store:
        counts = ShaclRunner(
            g, shapes_dir="shacl", store=store, backend="oxigraph"
        ).run()
        rows = store._conn.execute(
            "SELECT * FROM traces ORDER BY rowid ASC"
        ).fetchall()
    for r in rows:
        e = _row_to_entry(r).model_dump()
        per_shape[(e["shacl_shape"] or "?").rsplit("/", 1)[-1]] += 1
        per_subject[e["subject"]] += 1
    return counts["total"] == 0, per_shape, per_subject, True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/real_sdtm/synta")
    ap.add_argument("--tag", default="synta")
    ap.add_argument("--max-subjects", type=int, default=0, help="0 = all")
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--backend",
        choices=["pyshacl", "oxigraph"],
        default="oxigraph",
        help="L1 backend; oxigraph avoids the rdflib GROUP BY blowup (G2)",
    )
    a = ap.parse_args(argv)

    t0 = time.time()
    g = load_xpt_to_graph(a.src)
    enrich_recist_graph(g)
    n_subj_all = len({str(o) for _, o in g.subject_objects(CAVE["USUBJID"])})
    if a.max_subjects:
        g = _subset(g, a.max_subjects)
    n_subj = len({str(o) for _, o in g.subject_objects(CAVE["USUBJID"])})
    t_load = time.time() - t0

    t1 = time.time()
    conforms, per_shape, per_subject, report_ok = _validate(g, a.backend)
    t_val = time.time() - t1

    # Bucket shapes: separate semantic RECIST contradiction signal from
    # structural/SDTM-conformance flags (artifacts of a partial TU/TR/RS mapping
    # with no TA/SUPP* domains and non-standard date/seq vars).
    buckets: dict[str, Counter] = {
        "recist_derivation": Counter(),  # S1-S8 RECIST math/logic — the signal
        "archetype": Counter(),          # A01-A20 contradiction detectors
        "core_structural": Counter(),    # CORE-* SDTM conformance
        "anon_property": Counter(),      # blank-node sh:property constraints
    }
    for shape, n in per_shape.items():
        if shape.startswith("Shape_RECIST_") or shape.startswith("RECIST_"):
            buckets["recist_derivation"][shape] += n
        elif "Archetype_A" in shape:
            buckets["archetype"][shape] += n
        elif "CORE-" in shape:
            buckets["core_structural"][shape] += n
        else:
            buckets["anon_property"][shape] += n
    bucket_totals = {k: int(sum(v.values())) for k, v in buckets.items()}

    result = {
        "tag": a.tag,
        "backend": a.backend,
        "n_subjects_total": n_subj_all,
        "n_subjects_run": n_subj,
        "triples": len(g),
        "conforms": bool(conforms),
        "report_is_graph": report_ok,
        "total_flags": int(sum(per_shape.values())),
        "bucket_totals": bucket_totals,
        "flags_per_shape": dict(per_shape.most_common()),
        "recist_signal_shapes": dict(buckets["recist_derivation"].most_common()),
        "archetype_shapes": dict(buckets["archetype"].most_common()),
        "flagged_subjects": len(per_subject),
        "top_flagged_subjects": dict(per_subject.most_common(10)),
        "timing_sec": {"load": round(t_load, 1), "validate": round(t_val, 1)},
    }
    out = Path(a.out) if a.out else Path(f"eval/real_data_e1_{a.tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    summary = {k: v for k, v in result.items()
               if k not in ("flags_per_shape", "archetype_shapes")}
    print(json.dumps(summary, indent=2))
    print("->", out)


if __name__ == "__main__":
    main()
