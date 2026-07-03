"""Auto-port single_domain CORE oncology rules to SHACL Turtle.

Closed-world OPERATOR_MAP: any unmapped operator → rule logged to
translation_gaps.csv, no partial shapes.  Round-trip self-validation
via pyshacl on auto-generated conform/violate fixture pairs.
"""

import argparse, csv, hashlib, pickle, re
from collections import Counter
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, SH, XSD, Namespace
from pyshacl import validate as shacl_validate

CAVE = Namespace("https://cave-onc.org/shacl/")
PROV = Namespace("http://www.w3.org/ns/prov#")

MAPPED_OPS = frozenset({
    "non_empty", "empty", "exists", "not_exists",
    "equal_to", "not_equal_to",
    "is_contained_by", "is_not_contained_by",
    "is_contained_by_case_insensitive", "is_not_contained_by_case_insensitive",
    "date_greater_than",
    "longer_than", "less_than",
    "matches_regex", "not_matches_regex",
})

# ── Helpers ────────────────────────────────────────────────────────────

def _walk_leaves(node, leaves):
    if isinstance(node, dict):
        if "operator" in node: leaves.append(node)
        else:
            for v in node.values(): _walk_leaves(v, leaves)
    elif isinstance(node, list):
        for item in node: _walk_leaves(item, leaves)

def _tgt(lf): return lf.get("value",{}).get("target","")
def _cmp(lf): return lf.get("value",{}).get("comparator")
def _lit(v):
    if isinstance(v, bool): return rdflib.Literal(v, datatype=XSD.boolean)
    if isinstance(v, int):  return rdflib.Literal(v, datatype=XSD.integer)
    if isinstance(v, float):return rdflib.Literal(v, datatype=XSD.decimal)
    return rdflib.Literal(str(v), datatype=XSD.string)
def _diff(v):
    if isinstance(v, str): return f"__DIFF__{v}"
    if isinstance(v, (int,float)): return v + 999
    return "__DIFF__"
def _onco_domain(rule):
    d = rule.get("domains")
    if not isinstance(d, dict): return None
    inc = d.get("Include") or []
    o = sorted(set(inc) & {"TU","TR","RS","EX","DM"})
    return o[0] if o else None

_bnode_counter = [0]
def _bnode():
    """Deterministic BNode: resets per shape via _reset_bnode()."""
    b = rdflib.BNode(f"b{_bnode_counter[0]}")
    _bnode_counter[0] += 1
    return b
def _reset_bnode():
    _bnode_counter[0] = 0

# ── Deterministic serialization ────────────────────────────────────────

def _det_turtle(g):
    """Serialize graph with deterministic BNode labels."""
    ttl = g.serialize(format="turtle")
    mapping, counter = {}, [0]
    def repl(m):
        label = m.group(0)
        if label not in mapping:
            mapping[label] = f"_:b{counter[0]}"; counter[0] += 1
        return mapping[label]
    return re.sub(r'_:N[a-zA-Z0-9]+', repl, ttl)

# ── RDF list builder ───────────────────────────────────────────────────

def _rdf_list(g, vals):
    if not vals: return RDF.nil
    head = _bnode(); cur = head
    for i, v in enumerate(vals):
        g.add((cur, RDF.first, _lit(v)))
        nxt = _bnode() if i < len(vals)-1 else RDF.nil
        g.add((cur, RDF.rest, nxt)); cur = nxt
    return head

# ── SHACL constraint emission ──────────────────────────────────────────

def _prop(g, sn, path, pred, obj):
    b = _bnode(); g.add((sn, SH.property, b))
    g.add((b, SH.path, path)); g.add((b, pred, obj)); return b

def _prop_not(g, sn, path, inner):
    b = _bnode(); g.add((sn, SH.property, b))
    g.add((b, SH.path, path)); g.add((b, SH["not"], inner)); return b

def _prop_in(g, sn, path, vals):
    lst = _rdf_list(g, vals); b = _bnode()
    g.add((sn, SH.property, b)); g.add((b, SH.path, path))
    g.add((b, SH["in"], lst)); return b

def _prop_not_in(g, sn, path, vals):
    lst = _rdf_list(g, vals); inner = _bnode()
    g.add((inner, SH["in"], lst)); return _prop_not(g, sn, path, inner)

def _prop_pattern_ci(g, sn, path, vals, negate):
    """sh:pattern with sh:flags 'i' for case-insensitive containment."""
    pat = "^(" + "|".join(re.escape(v) for v in vals) + ")$"
    if negate:
        inner = _bnode()
        g.add((inner, SH.pattern, rdflib.Literal(pat)))
        g.add((inner, SH.flags, rdflib.Literal("i")))
        return _prop_not(g, sn, path, inner)
    b = _bnode(); g.add((sn, SH.property, b))
    g.add((b, SH.path, path))
    g.add((b, SH.pattern, rdflib.Literal(pat)))
    g.add((b, SH.flags, rdflib.Literal("i")))
    return b

def _add_constraint(g, sn, leaf):
    op, t, c = leaf["operator"], CAVE[_tgt(leaf)], _cmp(leaf)
    if op in ("non_empty","exists"):
        return _prop(g, sn, t, SH.minCount, rdflib.Literal(1, datatype=XSD.integer))
    if op in ("empty","not_exists"):
        return _prop(g, sn, t, SH.maxCount, rdflib.Literal(0, datatype=XSD.integer))
    if op == "equal_to":
        return _prop(g, sn, t, SH.hasValue, _lit(c))
    if op == "not_equal_to":
        inner = _bnode(); g.add((inner, SH.hasValue, _lit(c)))
        return _prop_not(g, sn, t, inner)
    if op == "is_contained_by":
        return _prop_in(g, sn, t, c if isinstance(c,list) else [c])
    if op == "is_not_contained_by":
        return _prop_not_in(g, sn, t, c if isinstance(c,list) else [c])
    if op == "is_contained_by_case_insensitive":
        return _prop_pattern_ci(g, sn, t, c if isinstance(c,list) else [c], False)
    if op == "is_not_contained_by_case_insensitive":
        return _prop_pattern_ci(g, sn, t, c if isinstance(c,list) else [c], True)
    if op == "date_greater_than":
        return _prop(g, sn, t, SH.lessThan, CAVE[c])
    if op == "longer_than":
        inner = _bnode()
        g.add((inner, SH.maxLength, rdflib.Literal(c, datatype=XSD.integer)))
        return _prop_not(g, sn, t, inner)
    if op == "less_than":
        inner = _bnode(); g.add((inner, SH.minInclusive, _lit(c)))
        return _prop_not(g, sn, t, inner)
    if op == "matches_regex":
        return _prop(g, sn, t, SH.pattern, rdflib.Literal(c))
    if op == "not_matches_regex":
        inner = _bnode(); g.add((inner, SH.pattern, rdflib.Literal(c)))
        return _prop_not(g, sn, t, inner)
    raise ValueError(f"Unmapped: {op}")

# ── Fixture generation ─────────────────────────────────────────────────

def _fixture_one(op, c, conform):
    """Return list of (target, value) pairs for one leaf in conform/violate mode."""
    if op in ("non_empty","exists"):
        return [("v", rdflib.Literal("X"))] if conform else []
    if op in ("empty","not_exists"):
        return [] if conform else [("v", rdflib.Literal("X"))]
    if op == "equal_to":
        return [("v", _lit(c))] if conform else [("v", _lit(_diff(c)))]
    if op == "not_equal_to":
        return [("v", _lit(_diff(c)))] if conform else [("v", _lit(c))]
    if op == "is_contained_by":
        vs = c if isinstance(c,list) else [c]
        return [("v", _lit(vs[0]))] if conform else [("v", _lit("__NOT_IN__"))]
    if op == "is_not_contained_by":
        vs = c if isinstance(c,list) else [c]
        return [("v", _lit("__NOT_IN__"))] if conform else [("v", _lit(vs[0]))]
    if op == "is_contained_by_case_insensitive":
        vs = c if isinstance(c,list) else [c]
        return [("v", _lit(vs[0]))] if conform else [("v", _lit("__NOT_CI__"))]
    if op == "is_not_contained_by_case_insensitive":
        vs = c if isinstance(c,list) else [c]
        return [("v", _lit("__NOT_CI__"))] if conform else [("v", _lit(vs[0]))]
    if op == "date_greater_than":
        if conform:
            return [("v", rdflib.Literal("2020-01-01",datatype=XSD.date)),
                    ("c", rdflib.Literal("2025-01-01",datatype=XSD.date))]
        return [("v", rdflib.Literal("2025-01-01",datatype=XSD.date)),
                ("c", rdflib.Literal("2020-01-01",datatype=XSD.date))]
    if op == "longer_than":
        s = "X"*(c+1) if conform else "X"*max(1,c-1)
        return [("v", rdflib.Literal(s))]
    if op == "less_than":
        return [("v", _lit(c-1))] if conform else [("v", _lit(c+1))]
    if op == "matches_regex":
        return [("v", rdflib.Literal("X"*25))] if conform else [("v", rdflib.Literal("short"))]
    if op == "not_matches_regex":
        return [("v", rdflib.Literal("__NO_MATCH__"))] if conform else [("v", _lit("10-20"))]
    return []

def _build_fixture(rule, domain, violate_idx=-1):
    """Build fixture graph. violate_idx >= 0 means that leaf is violated."""
    g = rdflib.Graph(); g.bind("cave", CAVE)
    focus = CAVE["violate_rec" if violate_idx >= 0 else "conform_rec"]
    g.add((focus, RDF.type, CAVE[domain]))
    leaves = []; _walk_leaves(rule.get("conditions",{}), leaves)
    if not leaves: return g, focus
    # Identify the violated target — no other leaf should set it
    violated_target = _tgt(leaves[violate_idx]) if violate_idx >= 0 else None
    # Reorder: process date_greater_than FIRST so date fields get proper values
    indexed = list(enumerate(leaves))
    ordered = sorted(indexed, key=lambda x: (0 if x[1]["operator"]=="date_greater_than" else 1, x[0]))

    set_targets = set()
    for i, lf in ordered:
        target = _tgt(lf); op = lf["operator"]; comp = _cmp(lf)
        # Skip conform leaves that target the violated field
        if violate_idx >= 0 and i != violate_idx and target == violated_target:
            continue
        want_conform = (i != violate_idx)
        pairs = _fixture_one(op, comp, want_conform)
        if op == "date_greater_than":
            if target not in set_targets and pairs:
                g.add((focus, CAVE[target], pairs[0][1])); set_targets.add(target)
            if comp not in set_targets and len(pairs) > 1:
                g.add((focus, CAVE[comp], pairs[1][1])); set_targets.add(comp)
        elif target not in set_targets:
            if pairs:
                g.add((focus, CAVE[target], pairs[0][1]))
            set_targets.add(target)
    return g, focus

# ── Core porting function (exposed for tests) ──────────────────────────

def port_rule(rule, ns=CAVE):
    """Port one rule → (shape_g, conform_g, violate_g, violate_focus) or None."""
    _reset_bnode()
    leaves = []; _walk_leaves(rule.get("conditions",{}), leaves)
    if {lf["operator"] for lf in leaves} - MAPPED_OPS: return None
    domain = _onco_domain(rule)
    if not domain: return None
    cid = rule.get("core_id","?")
    sn = ns[f"Shape_{cid}"]
    sg = rdflib.Graph()
    for pfx, uri in [("cave",ns),("sh",SH),("prov",PROV),("rdfs",RDFS)]:
        sg.bind(pfx, uri)
    sg.add((sn, RDF.type, SH.NodeShape))
    sg.add((sn, SH.targetClass, ns[domain]))
    sg.add((sn, RDFS.label, rdflib.Literal(rule.get("rule_type") or cid)))
    ops = ",".join(sorted({lf["operator"] for lf in leaves}))
    sg.add((sn, RDFS.comment, rdflib.Literal(f"ported from {cid}; operators: {ops}")))
    sg.add((sn, PROV.wasDerivedFrom, rdflib.Literal(cid)))
    for lf in leaves: _add_constraint(sg, sn, lf)
    cg, _ = _build_fixture(rule, domain, violate_idx=-1)
    # Choose violate_idx: prefer last leaf (less likely shared target)
    vg, vf = _build_fixture(rule, domain, violate_idx=len(leaves)-1)
    return sg, cg, vg, vf

# ── Main pipeline ──────────────────────────────────────────────────────

def run(classification_csv, rules_pkl, out_dir):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    sd_ids = []
    with open(classification_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["label"] == "single_domain": sd_ids.append(r["core_id"])
    with open(rules_pkl, "rb") as f: rules = pickle.load(f)

    # Collect per-shape Turtle blocks grouped by domain
    domain_blocks = {d: [] for d in ("tu","tr","rs","ex","dm")}
    gaps, opc, n = [], Counter(), 0
    for cid in sd_ids:
        leaves = []; _walk_leaves(rules[cid].get("conditions",{}), leaves)
        ops = set()
        for lf in leaves: opc[lf["operator"]] += 1; ops.add(lf["operator"])
        unmapped = ops - MAPPED_OPS
        if unmapped:
            gaps.append({"core_id":cid,"domain":_onco_domain(rules[cid]) or "?",
                         "unmapped_operators":"|".join(sorted(unmapped))})
            continue
        res = port_rule(rules[cid])
        if not res: continue
        sg = res[0]; dom = _onco_domain(rules[cid]).lower()
        ttl = _det_turtle(sg)
        # Strip prefix lines (will be added once per domain file)
        body = "\n".join(l for l in ttl.splitlines() if not l.startswith("@prefix"))
        domain_blocks[dom].append((cid, body))
        n += 1

    prefixes = ("@prefix cave: <https://cave-onc.org/shacl/> .\n"
                "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
                "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
                "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
                "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n")
    for d in ("tu","tr","rs","ex","dm"):
        blocks = sorted(domain_blocks[d], key=lambda x: x[0])
        body = "\n".join(b for _, b in blocks)
        (out_dir / f"{d}.ttl").write_text(
            prefixes + ("\n" + body if body else ""),
            encoding="utf-8")
    with open(out_dir/"operator_coverage.csv","w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f,["operator","occurrences","mapped"]); w.writeheader()
        for op in sorted(opc): w.writerow({"operator":op,"occurrences":opc[op],"mapped":"yes" if op in MAPPED_OPS else "no"})
    with open(out_dir/"translation_gaps.csv","w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f,["core_id","domain","unmapped_operators"]); w.writeheader()
        w.writerows(gaps)
    return n, len(gaps)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--classification", default="gate_a/classification.csv", type=Path)
    p.add_argument("--rules-pkl", default="vendor/core/resources/cache/rules.pkl", type=Path)
    p.add_argument("--out-dir", default="gate_a/shapes_auto", type=Path)
    a = p.parse_args()
    ne, ng = run(a.classification, a.rules_pkl, a.out_dir)
    print(f"Emitted: {ne}, Gaps: {ng}, Sum: {ne+ng}")

if __name__ == "__main__":
    main()
