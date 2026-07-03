"""Curate auto-ported SHACL shapes: polarity audit + primitive normalization.

Reads auto-ported shapes via port_rule(), applies CURATION table transforms,
writes gate_a/shapes/{tu,tr,rs,ex,dm}.ttl + curation_log.csv.

Curation kinds (closed set):
  polarity_flip | primitive_normalize | comment_clarify | prefix_align | no_change
"""

import csv, pickle, re
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, SH, XSD, Namespace

from scripts.port_to_shacl import (
    port_rule, _onco_domain, _det_turtle, _reset_bnode,
    _walk_leaves, CAVE, PROV,
)

# ── CURATION TABLE ────────────────────────────────────────────────────
# core_id → [(kind, rationale), ...]
# Every shape MUST appear at least once (no_change if pristine).

_FLIP_R = ("conditions=violation trigger; actions=generate_dataset_error_objects; "
           "rule_type=Record Data (no not_ wrapper); single-leaf → per-heuristic flip")
_DATE_R = ("date_greater_than already polarity-correct (sh:lessThan); "
           "non_empty guards preserve applicability scope")
_MULTI_R = ("multi-leaf rule; per-constraint polarity flip incompatible with "
            "fixture-swap round-trip invariant; deferred to follow-up De Morgan pass")
_IMPOSS_R = ("same-field compound constraints produce contradictory SHACL "
             "after per-constraint flip; requires sh:or treatment; deferred")

# 30 single-leaf rules → polarity_flip
_FLIP_IDS = frozenset({
    "CORE-000003", "CORE-000010", "CORE-000068", "CORE-000069", "CORE-000070",
    "CORE-000071", "CORE-000073", "CORE-000076", "CORE-000077", "CORE-000078",
    "CORE-000088", "CORE-000115", "CORE-000174", "CORE-000175", "CORE-000176",
    "CORE-000185", "CORE-000310", "CORE-000326",
    "CORE-000631", "CORE-000632", "CORE-000633", "CORE-000634", "CORE-000635",
    "CORE-000636", "CORE-000637", "CORE-000638", "CORE-000639", "CORE-000640",
    "CORE-000641", "CORE-000721",
})

# 5 date rules → no_change (already polarity-correct)
_DATE_IDS = frozenset({
    "CORE-000658", "CORE-000711", "CORE-000713", "CORE-000714", "CORE-000760",
})

# 4 impossible same-field rules → no_change (deferred)
_IMPOSS_IDS = frozenset({
    "CORE-000006", "CORE-000493", "CORE-000903", "CORE-000726",
})

def _build_curation(all_sd_ids):
    cur = {}
    for cid in all_sd_ids:
        if cid in _FLIP_IDS:
            cur[cid] = [("polarity_flip", _FLIP_R)]
        elif cid in _DATE_IDS:
            cur[cid] = [("no_change", _DATE_R)]
        elif cid in _IMPOSS_IDS:
            cur[cid] = [("no_change", _IMPOSS_R)]
        else:
            cur[cid] = [("no_change", _MULTI_R)]
    return cur

# ── Polarity flip transform ──────────────────────────────────────────

def _flip_property(g, bn):
    """Negate a single sh:property constraint on blank node bn."""
    # sh:minCount 1 → sh:maxCount 0  (exists / non_empty)
    mc = g.value(bn, SH.minCount)
    if mc is not None and mc.toPython() == 1:
        g.remove((bn, SH.minCount, mc))
        g.add((bn, SH.maxCount, rdflib.Literal(0, datatype=XSD.integer)))
        return

    # sh:maxCount 0 → sh:minCount 1  (empty / not_exists)
    xc = g.value(bn, SH.maxCount)
    if xc is not None and xc.toPython() == 0:
        g.remove((bn, SH.maxCount, xc))
        g.add((bn, SH.minCount, rdflib.Literal(1, datatype=XSD.integer)))
        return

    # sh:not [ inner ] → unwrap inner triples to bn  (all negated ops)
    not_node = g.value(bn, SH["not"])
    if not_node is not None:
        for p, o in list(g.predicate_objects(not_node)):
            g.remove((not_node, p, o))
            g.add((bn, p, o))
        g.remove((bn, SH["not"], not_node))
        return

    # sh:hasValue X → sh:not [ sh:hasValue X ]  (equal_to)
    hv = g.value(bn, SH.hasValue)
    if hv is not None:
        g.remove((bn, SH.hasValue, hv))
        inner = rdflib.BNode()
        g.add((inner, SH.hasValue, hv))
        g.add((bn, SH["not"], inner))
        return

    # sh:in (...) → sh:not [ sh:in (...) ]  (is_contained_by)
    in_list = g.value(bn, SH["in"])
    if in_list is not None:
        g.remove((bn, SH["in"], in_list))
        inner = rdflib.BNode()
        g.add((inner, SH["in"], in_list))
        g.add((bn, SH["not"], inner))
        return

    # sh:pattern + sh:flags → sh:not [ sh:pattern + sh:flags ]  (CI containment)
    pat = g.value(bn, SH.pattern)
    flg = g.value(bn, SH.flags)
    if pat is not None and flg is not None:
        g.remove((bn, SH.pattern, pat))
        g.remove((bn, SH.flags, flg))
        inner = rdflib.BNode()
        g.add((inner, SH.pattern, pat))
        g.add((inner, SH.flags, flg))
        g.add((bn, SH["not"], inner))
        return

    # sh:pattern (no flags) → sh:not [ sh:pattern ]  (matches_regex)
    if pat is not None:
        g.remove((bn, SH.pattern, pat))
        inner = rdflib.BNode()
        g.add((inner, SH.pattern, pat))
        g.add((bn, SH["not"], inner))
        return

    # sh:lessThan URI → sh:not [ sh:lessThan URI ]  (date_greater_than flip)
    lt = g.value(bn, SH.lessThan)
    if lt is not None:
        g.remove((bn, SH.lessThan, lt))
        inner = rdflib.BNode()
        g.add((inner, SH.lessThan, lt))
        g.add((bn, SH["not"], inner))
        return


def _flip_shape(sg):
    """Apply polarity flip to all sh:property constraints of a NodeShape."""
    for shape in sg.subjects(RDF.type, SH.NodeShape):
        for prop_bn in list(sg.objects(shape, SH.property)):
            _flip_property(sg, prop_bn)


def _normalize_shape(sg):
    """Cosmetic: sh:not [ sh:maxLength N ] → sh:minLength N+1;
    sh:not [ sh:minInclusive C ] → sh:maxExclusive C."""
    for shape in sg.subjects(RDF.type, SH.NodeShape):
        for prop_bn in list(sg.objects(shape, SH.property)):
            not_node = sg.value(prop_bn, SH["not"])
            if not_node is None:
                continue
            # sh:not [ sh:maxLength N ] → sh:minLength N+1
            mxl = sg.value(not_node, SH.maxLength)
            if mxl is not None:
                sg.remove((not_node, SH.maxLength, mxl))
                sg.remove((prop_bn, SH["not"], not_node))
                sg.add((prop_bn, SH.minLength,
                        rdflib.Literal(mxl.toPython() + 1, datatype=XSD.integer)))
                continue
            # sh:not [ sh:minInclusive C ] → sh:maxExclusive C
            mic = sg.value(not_node, SH.minInclusive)
            if mic is not None:
                sg.remove((not_node, SH.minInclusive, mic))
                sg.remove((prop_bn, SH["not"], not_node))
                sg.add((prop_bn, SH.maxExclusive, mic))


# ── Helpers ───────────────────────────────────────────────────────────

def _ops_str(rule):
    leaves = []
    _walk_leaves(rule.get("conditions", {}), leaves)
    ops = sorted({lf["operator"] for lf in leaves})
    return ",".join(ops)


# ── Main pipeline ─────────────────────────────────────────────────────

PREFIXES = (
    "@prefix cave: <https://cave-onc.org/shacl/> .\n"
    "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


def run(classification_csv, rules_pkl, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(rules_pkl, "rb") as f:
        rules = pickle.load(f)

    sd_ids = []
    with open(classification_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["label"] == "single_domain":
                sd_ids.append(r["core_id"])

    curation = _build_curation(sd_ids)

    domain_blocks = {d: [] for d in ("tu", "tr", "rs", "ex", "dm")}
    log_rows = []

    for cid in sd_ids:
        rule = rules[cid]
        entries = curation.get(cid, [("no_change", "")])
        ops_auto = _ops_str(rule)

        res = port_rule(rule)
        if not res:
            continue
        sg = res[0]

        flipped = False
        for kind, rationale in entries:
            if kind == "polarity_flip":
                _flip_shape(sg)
                flipped = True
            log_rows.append({
                "core_id": cid,
                "kind": kind,
                "from": ops_auto if kind == "polarity_flip" else "",
                "to": "polarity-inverted" if kind == "polarity_flip" else "",
                "rationale": rationale,
            })

        # Primitive normalization (always applied, cosmetic)
        pre_norm = _det_turtle(sg)
        _normalize_shape(sg)
        post_norm = _det_turtle(sg)
        if pre_norm != post_norm:
            log_rows.append({
                "core_id": cid,
                "kind": "primitive_normalize",
                "from": "sh:not [ sh:maxLength/minInclusive ]",
                "to": "sh:minLength/sh:maxExclusive",
                "rationale": "cosmetic: positive SHACL primitive form",
            })

        ttl = _det_turtle(sg)
        body = "\n".join(
            l for l in ttl.splitlines() if not l.startswith("@prefix")
        )
        dom = _onco_domain(rule).lower()
        domain_blocks[dom].append((cid, body))

    # Write per-domain .ttl files (sorted by core_id for determinism)
    for d in ("tu", "tr", "rs", "ex", "dm"):
        blocks = sorted(domain_blocks[d], key=lambda x: x[0])
        body = "\n".join(b for _, b in blocks)
        (out_dir / f"{d}.ttl").write_text(
            PREFIXES + ("\n" + body if body else ""),
            encoding="utf-8",
        )

    # Write curation log
    log_path = out_dir / "curation_log.csv"
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["core_id", "kind", "from", "to", "rationale"])
        w.writeheader()
        w.writerows(log_rows)

    n_flip = sum(1 for r in log_rows if r["kind"] == "polarity_flip")
    n_keep = sum(1 for r in log_rows if r["kind"] == "no_change")
    print(f"Curated: {n_flip} flipped, {n_keep} no_change, total {n_flip + n_keep}")


def main():
    from argparse import ArgumentParser
    p = ArgumentParser()
    p.add_argument("--classification", default="gate_a/classification.csv")
    p.add_argument("--rules-pkl", default="vendor/core/resources/cache/rules.pkl")
    p.add_argument("--out-dir", default="gate_a/shapes")
    a = p.parse_args()
    run(a.classification, a.rules_pkl, a.out_dir)


if __name__ == "__main__":
    main()
