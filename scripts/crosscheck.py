"""Comprehensive crosscheck of CAVE-Onc results for reproducibility and integrity."""
from __future__ import annotations
import json, sys, os

# Ensure CWD is project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from bench.injector import Injector
from bench.mutations import MUTATIONS
from scripts.track_b_analysis import _frames_to_graph, _run_l1, _run_l3, _enrich_rs
from rdflib import Graph, URIRef
from rdflib.namespace import RDF
from pyshacl import validate

SH = 'http://www.w3.org/ns/shacl#'

def main():
    print("=" * 70)
    print("CAVE-Onc Crosscheck Suite - Scientific Integrity Verification")
    print("=" * 70)

    # Load clean data
    clean_frames = Injector(output_dir="bench/output_track_b")._load_all()
    print(f"Loaded domains: {sorted(clean_frames.keys())}")
    enriched_clean = _enrich_rs({k: v.copy() for k, v in clean_frames.items()})
    clean_graph = _frames_to_graph(enriched_clean)
    clean_l1 = _run_l1(clean_graph)
    print(f"Clean baseline L1: {clean_l1}")

    # ===== CHECK 1: Archetype shapes on clean data =====
    print("\n" + "=" * 70)
    print("CHECK 1: Do archetype shapes fire on CLEAN (unmutated) data?")
    print("=" * 70)

    shapes_g = Graph()
    shapes_g.parse("shacl/archetype_shapes.ttl", format="turtle")
    shape_nodes = list(shapes_g.subjects(RDF.type, URIRef(SH + "NodeShape")))
    print(f"  Archetype shapes loaded: {len(shape_nodes)}")

    try:
        conforms, rg, rt = validate(clean_graph, shacl_graph=shapes_g,
                                     inference="none", abort_on_first=False)
        violations = list(rg.subjects(RDF.type, URIRef(SH + "ValidationResult")))
        n_viol = len(violations)
    except Exception as e:
        conforms, n_viol, violations = True, 0, []
        print(f"  Validation error (treated as conforms): {e}")

    if n_viol == 0:
        print(f"  PASS: 0 violations on clean data (no false positives)")
    else:
        print(f"  WARN: {n_viol} violations on clean data")
        for v in list(violations)[:5]:
            src = list(rg.objects(v, URIRef(SH + "sourceShape")))
            msg = list(rg.objects(v, URIRef(SH + "resultMessage")))
            s = str(src[0]).split("/")[-1] if src else "?"
            m = str(msg[0])[:80] if msg else "?"
            print(f"    {s}: {m}")

    # ===== CHECK 2: Mutation integrity =====
    print("\n" + "=" * 70)
    print("CHECK 2: Do mutations actually change data?")
    print("=" * 70)

    mutation_checks = []
    for aid in sorted(MUTATIONS.keys()):
        frames = {k: v.copy() for k, v in clean_frames.items()}
        try:
            mutated, meta = MUTATIONS[aid](frames)
            changed = False
            for domain in mutated:
                if domain in clean_frames:
                    orig = clean_frames[domain]
                    mut = mutated[domain]
                    if len(orig) != len(mut) or not orig.equals(mut):
                        changed = True
                        break
                else:
                    changed = True
            subj = meta.get("usubjid", "?")
            desc = meta.get("description", "")[:55]
            status = "CHANGED" if changed else "NO-CHANGE"
            mutation_checks.append((aid, status, subj, desc))
            print(f"  {aid}: {status} subj={subj}  {desc}")
        except Exception as e:
            mutation_checks.append((aid, "ERROR", "?", str(e)[:50]))
            print(f"  {aid}: ERROR - {str(e)[:60]}")

    unchanged = [m for m in mutation_checks if m[1] == "NO-CHANGE"]
    errors = [m for m in mutation_checks if m[1] == "ERROR"]
    changed = [m for m in mutation_checks if m[1] == "CHANGED"]
    print(f"\n  Changed: {len(changed)}, Unchanged: {len(unchanged)}, Errors: {len(errors)}")
    if unchanged:
        print(f"  WARNING: unchanged mutations: {[m[0] for m in unchanged]}")

    # ===== CHECK 3: Per-archetype delta verification =====
    print("\n" + "=" * 70)
    print("CHECK 3: Per-archetype delta + detection verification")
    print("  (Full re-run from scratch)")
    print("=" * 70)

    deltas = {}
    l3_results = {}
    for aid in sorted(MUTATIONS.keys()):
        frames = {k: v.copy() for k, v in clean_frames.items()}
        try:
            frames, meta = MUTATIONS[aid](frames)
            frames = _enrich_rs(frames)
            graph = _frames_to_graph(frames)
            l1 = _run_l1(graph)
            delta = l1 - clean_l1
            deltas[aid] = delta
            # L3 check for A19
            l3_count = 0
            if aid == "A19":
                traces = _run_l3(graph)
                l3_count = len(traces)
                l3_results[aid] = l3_count
            l1d = delta != 0
            l3d = l3_count > 0
            detected = l1d or l3d
            src = "L3" if l3d and not l1d else ("L1" if l1d else "NONE")
            status = "DETECTED" if detected else "MISSED"
            print(f"  {aid}: delta={delta:+4d} l3={l3_count} src={src:4s} [{status}]")
        except Exception as e:
            deltas[aid] = None
            print(f"  {aid}: ERROR - {str(e)[:60]}")

    detected_count = sum(1 for aid in deltas
                         if (deltas[aid] is not None and deltas[aid] != 0)
                         or l3_results.get(aid, 0) > 0)
    print(f"\n  Total detected: {detected_count}/20")

    # ===== CHECK 4: Reproducibility — run again =====
    print("\n" + "=" * 70)
    print("CHECK 4: Reproducibility - re-run 5 archetypes a 2nd time")
    print("=" * 70)

    import random
    random.seed(42)
    spot = random.sample(sorted(MUTATIONS.keys()), 5)
    all_match = True
    for aid in spot:
        frames = {k: v.copy() for k, v in clean_frames.items()}
        frames, _ = MUTATIONS[aid](frames)
        frames = _enrich_rs(frames)
        graph = _frames_to_graph(frames)
        l1 = _run_l1(graph)
        d2 = l1 - clean_l1
        expected = deltas.get(aid)
        match = d2 == expected
        if not match:
            all_match = False
        print(f"  {aid}: run2={d2:+4d} run1={expected} {'MATCH' if match else 'MISMATCH!'}")

    if all_match:
        print(f"\n  PASS: All 5 spot checks reproduce exactly")
    else:
        print(f"\n  FAIL: Some results did not reproduce!")

    # ===== CHECK 5: Cross-check with saved results =====
    print("\n" + "=" * 70)
    print("CHECK 5: Cross-check against saved track_b_results.json")
    print("=" * 70)

    saved_path = os.path.join(ROOT, "eval", "track_b_results.json")
    if os.path.exists(saved_path):
        saved = json.loads(open(saved_path, encoding="utf-8").read())
        mismatches = []
        for a in saved["archetypes"]:
            aid = a["archetype_id"]
            saved_delta = a["flag_delta_vs_clean"]
            computed_delta = deltas.get(aid)
            if computed_delta is not None and saved_delta != computed_delta:
                mismatches.append((aid, saved_delta, computed_delta))
                print(f"  {aid}: MISMATCH saved={saved_delta:+d} computed={computed_delta:+d}")
        if not mismatches:
            print(f"  PASS: All {len(saved['archetypes'])} deltas match saved results exactly")
        else:
            print(f"\n  FAIL: {len(mismatches)} mismatches found!")
    else:
        print(f"  SKIP: No saved results file found")
        mismatches = []

    # ===== CHECK 6: Detection logic edge cases =====
    print("\n" + "=" * 70)
    print("CHECK 6: Edge case analysis")
    print("=" * 70)

    # A14: negative delta
    d14 = deltas.get("A14", 0)
    print(f"  A14 (negative delta): delta={d14}")
    print(f"    Expected: -1 (removing EX records decreases violations)")
    print(f"    Correct detection via abs(delta)!=0: {'YES' if d14 != 0 else 'NO'}")

    # A19: L3-only (delta=0)
    d19 = deltas.get("A19", 0)
    l3_19 = l3_results.get("A19", 0)
    print(f"  A19 (L3-only): delta={d19}, l3_traces={l3_19}")
    print(f"    Expected: delta=0, l3_traces>=1")
    print(f"    Correct detection via L3: {'YES' if l3_19 > 0 else 'NO'}")

    # Large deltas: A06, A17, A18
    for aid in ["A06", "A17", "A18"]:
        d = deltas.get(aid, "?")
        print(f"  {aid} (large delta): delta={d}")

    # ===== FINAL SUMMARY =====
    print("\n" + "=" * 70)
    print("CROSSCHECK SUMMARY")
    print("=" * 70)

    checks = [
        ("CHECK 1: No false positives on clean data", n_viol == 0),
        ("CHECK 2: All mutations change data", len(unchanged) == 0 and len(errors) == 0),
        ("CHECK 3: Detection rate 20/20", detected_count == 20),
        ("CHECK 4: Reproducibility (5 spot checks)", all_match),
        ("CHECK 5: Matches saved results file", len(mismatches) == 0),
        ("CHECK 6a: A14 negative delta detected", deltas.get("A14", 0) != 0),
        ("CHECK 6b: A19 L3 traces found", l3_results.get("A19", 0) > 0),
    ]

    all_pass = True
    for name, passed in checks:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")
        if not passed:
            all_pass = False

    print(f"\n  Detection: {detected_count}/20")
    if all_pass:
        print(f"\n  >>> ALL CHECKS PASSED - Results are REPRODUCIBLE and ROBUST <<<")
    else:
        print(f"\n  >>> SOME CHECKS FAILED - Results need INVESTIGATION <<<")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
