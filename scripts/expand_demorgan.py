"""Recursive De Morgan expansion for 50 deferred single_domain rules.

Reads conditions trees from rules.pkl, applies recursive negate() walker,
emits SHACL via recursive emitter, builds unified fixture pair, validates
with pyshacl round-trip, and replaces deferred shapes in gate_a/shapes/.

Closed-world contract: negate() and SHACL emitter follow the Design notes
pseudocode verbatim. Unknown node types → STOP with Q5.
"""

import csv, pickle, re, sys
from collections import Counter
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, SH, XSD
from pyshacl import validate as shacl_validate

from scripts.port_to_shacl import (
    port_rule, _onco_domain, _det_turtle, _reset_bnode,
    _walk_leaves, _bnode, _rdf_list,
    CAVE, PROV, MAPPED_OPS,
    _lit, _fixture_one, _tgt, _cmp,
)
from scripts.curate_shapes import (
    _flip_shape, _normalize_shape, PREFIXES,
    _FLIP_IDS, _DATE_IDS,
)

# ── Deferred ID derivation ─────────────────────────────────────────────

_DATE_RULE_IDS = frozenset({
    "CORE-000658", "CORE-000711", "CORE-000713", "CORE-000714", "CORE-000760",
})


def _load_deferred_ids(log_path):
    """Derive the 50 deferred core_ids: no_change rows minus date rules."""
    ids = set()
    with open(log_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] == "no_change" and r["core_id"] not in _DATE_RULE_IDS:
                ids.add(r["core_id"])
    return sorted(ids)

# ── Recursive negation (verbatim from Design notes) ────────────────────

_NODE_TYPE_LOG = Counter()


def negate(node):
    """Negate a conditions tree node recursively.

    Returns tagged tuple:
      ("flipped_leaf", original_leaf_dict)
      ("any_branch",  [negate(c1), negate(c2), ...])   # was all
      ("all_branch",  [negate(c1), negate(c2), ...])   # was any
    Raises ValueError on unknown node shape → caller must append Q5.
    """
    if isinstance(node, dict):
        if "operator" in node:
            _NODE_TYPE_LOG["leaf"] += 1
            return ("flipped_leaf", node)
        if "all" in node:
            _NODE_TYPE_LOG["all"] += 1
            return ("any_branch", [negate(c) for c in node["all"]])
        if "any" in node:
            _NODE_TYPE_LOG["any"] += 1
            return ("all_branch", [negate(c) for c in node["any"]])
        raise ValueError(f"Unknown node: keys={sorted(node.keys())}")
    raise ValueError(f"Unknown node type: {type(node)}")

# ── Negated constraint emission ────────────────────────────────────────

def _emit_negated_prop(g, parent, leaf):
    """Emit sh:property block with the negated constraint for a leaf."""
    op = leaf["operator"]
    target = _tgt(leaf)
    comp = _cmp(leaf)
    path = CAVE[target]

    bn = _bnode()
    g.add((parent, SH.property, bn))
    g.add((bn, SH.path, path))

    if op in ("non_empty", "exists"):
        g.add((bn, SH.maxCount, rdflib.Literal(0, datatype=XSD.integer)))
    elif op in ("empty", "not_exists"):
        g.add((bn, SH.minCount, rdflib.Literal(1, datatype=XSD.integer)))
    elif op == "equal_to":
        inner = _bnode()
        g.add((inner, SH.hasValue, _lit(comp)))
        g.add((bn, SH["not"], inner))
    elif op == "not_equal_to":
        g.add((bn, SH.hasValue, _lit(comp)))
    elif op == "is_contained_by":
        vals = comp if isinstance(comp, list) else [comp]
        lst = _rdf_list(g, vals)
        inner = _bnode()
        g.add((inner, SH["in"], lst))
        g.add((bn, SH["not"], inner))
    elif op == "is_not_contained_by":
        vals = comp if isinstance(comp, list) else [comp]
        lst = _rdf_list(g, vals)
        g.add((bn, SH["in"], lst))
    elif op == "longer_than":
        g.add((bn, SH.maxLength, rdflib.Literal(comp, datatype=XSD.integer)))
    elif op == "not_matches_regex":
        g.add((bn, SH.pattern, rdflib.Literal(comp)))
    elif op == "matches_regex":
        inner = _bnode()
        g.add((inner, SH.pattern, rdflib.Literal(comp)))
        g.add((bn, SH["not"], inner))
    elif op == "date_greater_than":
        inner = _bnode()
        g.add((inner, SH.lessThan, CAVE[comp]))
        g.add((bn, SH["not"], inner))
    elif op == "less_than":
        g.add((bn, SH.minInclusive, _lit(comp)))
    elif op == "is_contained_by_case_insensitive":
        vals = comp if isinstance(comp, list) else [comp]
        pat = "^(" + "|".join(re.escape(v) for v in vals) + ")$"
        inner = _bnode()
        g.add((inner, SH.pattern, rdflib.Literal(pat)))
        g.add((inner, SH.flags, rdflib.Literal("i")))
        g.add((bn, SH["not"], inner))
    elif op == "is_not_contained_by_case_insensitive":
        vals = comp if isinstance(comp, list) else [comp]
        pat = "^(" + "|".join(re.escape(v) for v in vals) + ")$"
        g.add((bn, SH.pattern, rdflib.Literal(pat)))
        g.add((bn, SH.flags, rdflib.Literal("i")))
    else:
        raise ValueError(f"Cannot negate operator: {op}")

# ── RDF list of sub-shape nodes (for sh:or / sh:and) ──────────────────

def _rdf_list_nodes(g, nodes):
    """Create an RDF list of arbitrary RDF nodes. Returns head BNode."""
    if not nodes:
        return RDF.nil
    head = _bnode(); cur = head
    for i, n in enumerate(nodes):
        g.add((cur, RDF.first, n))
        nxt = _bnode() if i < len(nodes) - 1 else RDF.nil
        g.add((cur, RDF.rest, nxt)); cur = nxt
    return head

# ── SHACL emission (verbatim from Design notes) ───────────────────────

def emit_at_root(g, shape_node, neg_tree):
    """Emit the top-level negated tree as SHACL constraints on NodeShape."""
    tag, data = neg_tree
    if tag == "flipped_leaf":
        _emit_negated_prop(g, shape_node, data)
    elif tag == "all_branch":
        for child in data:
            if child[0] == "flipped_leaf":
                _emit_negated_prop(g, shape_node, child[1])
            elif child[0] == "any_branch":
                _emit_sh_or(g, shape_node, child[1])
            elif child[0] == "all_branch":
                _emit_sh_and(g, shape_node, child[1])
    elif tag == "any_branch":
        _emit_sh_or(g, shape_node, data)


def emit_branch(g, neg_tree):
    """Emit a branch of the negated tree as a SHACL sub-shape. Returns BNode."""
    tag, data = neg_tree
    if tag == "flipped_leaf":
        bn = _bnode()
        _emit_negated_prop(g, bn, data)
        return bn
    elif tag == "all_branch":
        bn = _bnode()
        for child in data:
            if child[0] == "flipped_leaf":
                _emit_negated_prop(g, bn, child[1])
            elif child[0] == "any_branch":
                _emit_sh_or(g, bn, child[1])
            elif child[0] == "all_branch":
                _emit_sh_and(g, bn, child[1])
        return bn
    elif tag == "any_branch":
        bn = _bnode()
        branches = [emit_branch(g, c) for c in data]
        lst = _rdf_list_nodes(g, branches)
        g.add((bn, SH["or"], lst))
        return bn


def _emit_sh_or(g, parent, children):
    branches = [emit_branch(g, c) for c in children]
    lst = _rdf_list_nodes(g, branches)
    g.add((parent, SH["or"], lst))


def _emit_sh_and(g, parent, children):
    branches = [emit_branch(g, c) for c in children]
    lst = _rdf_list_nodes(g, branches)
    g.add((parent, SH["and"], lst))

# ── Build De Morgan shape ──────────────────────────────────────────────

def build_demorgan_shape(rule):
    """Build the De Morgan expanded SHACL shape. Returns (sg, cid, domain)."""
    cid = rule.get("core_id", "?")
    cond = rule.get("conditions", {})
    domain = _onco_domain(rule)
    if not domain:
        raise ValueError(f"{cid}: no oncology domain")

    neg_tree = negate(cond)

    _reset_bnode()
    sg = rdflib.Graph()
    for pfx, uri in [("cave", CAVE), ("sh", SH), ("prov", PROV),
                      ("rdfs", RDFS), ("rdf", RDF), ("xsd", XSD)]:
        sg.bind(pfx, uri)

    sn = CAVE[f"Shape_{cid}"]
    sg.add((sn, RDF.type, SH.NodeShape))
    sg.add((sn, SH.targetClass, CAVE[domain]))
    sg.add((sn, RDFS.label, rdflib.Literal(rule.get("rule_type") or cid)))
    leaves = []; _walk_leaves(cond, leaves)
    ops = ",".join(sorted({lf["operator"] for lf in leaves}))
    sg.add((sn, RDFS.comment,
            rdflib.Literal(f"ported from {cid}; demorgan; operators: {ops}")))
    sg.add((sn, PROV.wasDerivedFrom, rdflib.Literal(cid)))

    emit_at_root(sg, sn, neg_tree)
    return sg, cid, domain

# ── Unified fixture generator ──────────────────────────────────────────

def build_demorgan_fixture(rule, domain, for_violate):
    """Build fixture graph for De Morgan expanded shape.

    for_violate=True:  emit each leaf's CONFORM value → trigger fires → violation
    for_violate=False: emit each leaf's VIOLATE value → trigger absent → conforms
    Same-field overlap: first leaf wins (same as port_to_shacl.py convention).
    """
    g = rdflib.Graph(); g.bind("cave", CAVE)
    focus = CAVE["violate_rec" if for_violate else "conform_rec"]
    g.add((focus, RDF.type, CAVE[domain]))

    leaves = []; _walk_leaves(rule.get("conditions", {}), leaves)
    set_targets = set()
    for lf in leaves:
        target = _tgt(lf)
        op = lf["operator"]; comp = _cmp(lf)
        pairs = _fixture_one(op, comp, for_violate)
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

# ── Category classification (matches Q4 in curation_open_questions.md) ─

_CAT_A_IDS = frozenset({
    "CORE-000031", "CORE-000032", "CORE-000648", "CORE-000883",
})
_CAT_B_IDS = frozenset({
    "CORE-000122", "CORE-000325", "CORE-000452", "CORE-000453",
    "CORE-000498", "CORE-000656", "CORE-000709", "CORE-000726",
    "CORE-001043",
})


def _classify_rule(cid):
    """Return category tag for curation log notes."""
    if cid in _CAT_A_IDS: return "cat_a_flat_and"
    if cid in _CAT_B_IDS: return "cat_b_nested"
    return "q1q2_flat_or"

# ── Main pipeline ──────────────────────────────────────────────────────

def run(classification_csv, rules_pkl, shapes_dir, log_path):
    shapes_dir = Path(shapes_dir)
    deferred_ids = _load_deferred_ids(log_path)
    if len(deferred_ids) != 50:
        print(f"STOP: expected 50 deferred IDs, got {len(deferred_ids)}", file=sys.stderr)
        sys.exit(1)

    with open(rules_pkl, "rb") as f:
        rules = pickle.load(f)

    sd_ids = []
    with open(classification_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["label"] == "single_domain": sd_ids.append(r["core_id"])

    deferred_set = set(deferred_ids)
    cat_counts = Counter()
    same_field_notes = 0
    domain_blocks = {d: [] for d in ("tu", "tr", "rs", "ex", "dm")}
    new_log_rows = []

    for cid in sd_ids:
        rule = rules[cid]
        dom = _onco_domain(rule).lower()

        if cid in deferred_set:
            sg, _, _ = build_demorgan_shape(rule)

            # Serialize BEFORE validation (pyshacl mutates the graph)
            ttl = _det_turtle(sg)
            body = "\n".join(l for l in ttl.splitlines()
                             if not l.startswith("@prefix"))

            # Validate using a fresh parse to avoid graph mutation
            sg_val = rdflib.Graph()
            sg_val.parse(data=ttl, format="turtle")
            cg, _ = build_demorgan_fixture(rule, dom.upper(), for_violate=False)
            vg, _ = build_demorgan_fixture(rule, dom.upper(), for_violate=True)

            conforms, _, rt = shacl_validate(
                cg, shacl_graph=sg_val, inference="none")
            if not conforms:
                neg_tree = negate(rule["conditions"])
                print(f"STOP: {cid} conform failed\n{rt}\nNegated tree: {neg_tree}",
                      file=sys.stderr)
                sys.exit(1)
            conforms2, _, rt2 = shacl_validate(
                vg, shacl_graph=sg_val, inference="none")
            if conforms2:
                neg_tree = negate(rule["conditions"])
                print(f"STOP: {cid} violate passed\n{rt2}\nNegated tree: {neg_tree}",
                      file=sys.stderr)
                sys.exit(1)

            leaves = []; _walk_leaves(rule.get("conditions", {}), leaves)
            targets = [_tgt(lf) for lf in leaves]
            has_overlap = len(targets) != len(set(targets))
            if has_overlap: same_field_notes += 1

            cat = _classify_rule(cid)
            cat_counts[cat] += 1
            notes = cat
            if has_overlap: notes += "; same_field_overlap"
            new_log_rows.append({
                "core_id": cid, "kind": "demorgan_or",
                "from": "", "to": "",
                "rationale": f"recursive De Morgan expansion; {notes}",
            })

            domain_blocks[dom].append((cid, body))
        else:
            res = port_rule(rule)
            if not res: continue
            sg = res[0]
            if cid in _FLIP_IDS: _flip_shape(sg)
            _normalize_shape(sg)
            ttl = _det_turtle(sg)
            body = "\n".join(l for l in ttl.splitlines() if not l.startswith("@prefix"))
            domain_blocks[dom].append((cid, body))

    for d in ("tu", "tr", "rs", "ex", "dm"):
        blocks = sorted(domain_blocks[d], key=lambda x: x[0])
        body = "\n".join(b for _, b in blocks)
        (shapes_dir / f"{d}.ttl").write_text(
            PREFIXES + ("\n" + body if body else ""), encoding="utf-8")

    # Rewrite curation log: keep pre-existing rows, replace old demorgan_or
    existing_rows = []
    with open(log_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] != "demorgan_or":
                existing_rows.append(r)
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["core_id", "kind", "from", "to", "rationale"])
        w.writeheader()
        w.writerows(existing_rows)
        w.writerows(new_log_rows)

    print(f"Expanded: {len(new_log_rows)}/50")
    print(f"Categories: {dict(sorted(cat_counts.items()))}")
    print(f"Same-field overlap: {same_field_notes}")
    print(f"Publishable: 35 + {len(new_log_rows)} = {35 + len(new_log_rows)}/85")


def main():
    from argparse import ArgumentParser
    p = ArgumentParser()
    p.add_argument("--classification", default="gate_a/classification.csv")
    p.add_argument("--rules-pkl", default="vendor/core/resources/cache/rules.pkl")
    p.add_argument("--shapes-dir", default="gate_a/shapes")
    p.add_argument("--log-path", default="gate_a/shapes/curation_log.csv")
    a = p.parse_args()
    run(a.classification, a.rules_pkl, a.shapes_dir, a.log_path)


if __name__ == "__main__":
    main()
