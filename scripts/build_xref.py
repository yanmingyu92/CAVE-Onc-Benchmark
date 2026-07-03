#!/usr/bin/env python
"""Build gate_a/xref_table.csv and gate_a/gap_rules.md — deterministic."""

from __future__ import annotations

import argparse, csv, pickle, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from rdflib import Graph, Namespace

ONC = {"TU", "TR", "RS", "EX", "DM"}
CAVE = "cave:Shape_"
PROV = Namespace("http://www.w3.org/ns/prov#")
FIELDS = ["core_rule_id", "label", "shape_iri", "domain",
          "port_kind", "complexity_tier", "gap_reason", "rule_description"]
TIER_DESCS = {
    "valueset": ("Rules whose conditions look up a value in a different domain's "
                 "codelist or sponsor-defined value set.",
                 "L1 SHACL-SPARQL (T1.5-style) for simple lookups; L2 DAG for probabilistic ones."),
    "existence": ("Rules whose conditions check for the existence of a record in a "
                  "different domain.",
                  "L1 SHACL-SPARQL (T1.5-style); L2 DAG for multi-hop existence."),
    "aggregate": ("Rules whose conditions require aggregated values (min, max, set) "
                  "from another domain.",
                  "L2 DAG (requires computed intermediates)."),
    "computed": ("Rules whose conditions depend on a computed variable derived from "
                 "another domain's data.",
                 "L2 DAG (requires derived-variable computation)."),
}


def _domain(inv: dict) -> str:
    doms = sorted({d.strip() for d in inv.get("domains_include", "").split(";") if d.strip()} & ONC)
    return "MULTI" if len(doms) > 1 else (doms[0] if doms else "")


def _refs(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj] if obj.startswith("$") else []
    if isinstance(obj, dict):
        return [r for v in obj.values() for r in _refs(v)]
    if isinstance(obj, list):
        return [r for v in obj for r in _refs(v)]
    return []


def _agg_ops(obj) -> list[str]:
    if isinstance(obj, dict):
        op = obj.get("operator", "")
        return ([op] if op in ("is_not_unique_set", "is_not_unique_relationship") else []) + \
               [o for v in obj.values() for o in _agg_ops(v)]
    if isinstance(obj, list):
        return [o for v in obj for o in _agg_ops(v)]
    return []


def _trunc(s: str, n: int = 100) -> str:
    return s if len(s) <= n else s[:n] + "\u2026"


def _csv_map(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["core_id"]: r for r in csv.DictReader(f)}


def _csv_list(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _shape_map(d: Path) -> dict[str, str]:
    g = Graph()
    for t in sorted(d.glob("*.ttl")):
        g.parse(t)
    return {str(o): f"{CAVE}{o}" for _, _, o in g.triples((None, PROV.wasDerivedFrom, None))}


def _fail(msg: str) -> None:
    print(f"STOP: {msg}", file=sys.stderr); sys.exit(1)


def _write_gap(path: Path, gd: str, tiers: dict, aggs: list,
               ns: int, nc: int, na: int, tc: Counter) -> None:
    nt = ns + nc + na
    L = ["# Gate A \u2014 Unportable rule gap report",
         f"Generated: {gd}; CORE v0.15 / commit 88837395.", "",
         "## Summary",
         f"- Total oncology rules in scope: {nt}",
         f"- Ported to SHACL (T1.4 + T1.4-R + T1.4-R2): {ns} ({ns/nt*100:.1f}%)",
         f"- Unportable: {nc+na} ({(nc+na)/nt*100:.1f}%)",
         f"  - Cross-domain: {nc} ({nc/nt*100:.1f}%) \u2014 by complexity tier:"]
    for t in ("valueset", "existence", "aggregate", "computed"):
        L.append(f"    - {t}: {tc[t]}")
    L += [f"  - Aggregate (uniqueness): {na} ({na/nt*100:.1f}%)", "",
          f"## Cross-domain rules ({nc})", ""]
    for t in ("valueset", "existence", "aggregate", "computed"):
        entries = tiers.get(t, [])
        desc, mit = TIER_DESCS[t]
        L += [f"### {t} ({len(entries)})", desc, f"Mitigation path: {mit}", "",
              "| core_id | domains | refs (target/value/comparator) | description |",
              "|---|---|---|---|"]
        for e in entries:
            L.append(f"| {e['core_id']} | {e['domains']} | {e['refs']} "
                     f"| {e['description'].replace('|', chr(92)+'|')} |")
        L.append("")
    L += [f"## Aggregate / uniqueness rules ({na})",
          "Rules using `is_not_unique_set` or `is_not_unique_relationship` "
          "operators that require row-set uniqueness reasoning. SHACL Core cannot express these.",
          "Mitigation: SHACL-SPARQL (count + group-by) \u2014 feasible for v2; not blocking Gate A.",
          "", "| core_id | domains | operator | description |", "|---|---|---|---|"]
    for e in aggs:
        L.append(f"| {e['core_id']} | {e['domains']} | {e['operator']} "
                 f"| {e['description'].replace('|', chr(92)+'|')} |")
    L += ["", "## Recommendation",
          f"- {ns}/{nt} ({ns/nt*100:.1f}%) port-success rate is the canonical Gate A figure.",
          "- 0 of the 85 ported rules required expressiveness compromise (T1.4-R2 closed at 0 gaps).",
          "- The 37 unportable rules form 2 publishable expressiveness-gap buckets:",
          f"  bucket 1 = cross-domain joins ({nc}, splits into 4 complexity tiers),",
          f"  bucket 2 = row-set uniqueness aggregation ({na}).",
          "- All 37 are addressed by CAVE-Onc's L1 SHACL-SPARQL + L2 DAG layers per `proposal.md` \u00a73."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    for k, v in [("--shapes-dir", "gate_a/shapes"), ("--classification", "gate_a/classification.csv"),
                 ("--inventory", "gate_a/rules_inventory.csv"),
                 ("--curation-log", "gate_a/shapes/curation_log.csv"),
                 ("--recist-catalog", "gate_a/recist_catalog.csv"),
                 ("--rules-pkl", "vendor/core/resources/cache/rules.pkl"),
                 ("--out-xref", "gate_a/xref_table.csv"), ("--out-gap", "gate_a/gap_rules.md")]:
        p.add_argument(k, default=v)
    p.add_argument("--date", default=date.today().isoformat())
    a = p.parse_args()

    shapes = _shape_map(Path(a.shapes_dir))
    kinds: dict[str, str] = {}
    with Path(a.curation_log).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            kinds[row["core_id"]] = row["kind"]
    inv = _csv_map(Path(a.inventory))
    cls = _csv_list(Path(a.classification))
    with open(a.rules_pkl, "rb") as f:
        pkl = pickle.load(f)

    if len(cls) != 122:
        _fail(f"classification has {len(cls)} rows, expected 122")
    missing = {r["core_id"] for r in cls if r["label"] == "single_domain"} - set(shapes)
    if missing:
        _fail(f"missing shape IRIs for: {sorted(missing)}")

    rows, tiers, aggs = [], defaultdict(list), []
    for r in sorted(cls, key=lambda x: x["core_id"]):
        cid, lab = r["core_id"], r["label"]
        d = _trunc(inv.get(cid, {}).get("description", ""))
        if lab == "single_domain":
            rows.append({"core_rule_id": cid, "label": lab, "shape_iri": shapes.get(cid, ""),
                         "domain": _domain(inv.get(cid, {})), "port_kind": kinds.get(cid, "no_change"),
                         "complexity_tier": "", "gap_reason": "", "rule_description": d})
        elif lab == "unportable_cross_domain":
            dom, tier = _domain(inv.get(cid, {})), r.get("complexity_tier", "")
            refs = ", ".join(sorted(set(_refs(pkl.get(cid, {}).get("conditions", {})))))
            tiers[tier].append({"core_id": cid, "domains": dom, "refs": refs, "description": d})
            rows.append({"core_rule_id": cid, "label": lab, "shape_iri": "",
                         "domain": dom, "port_kind": "none", "complexity_tier": tier,
                         "gap_reason": f"references $-prefixed variable from another domain: {refs}",
                         "rule_description": d})
        else:  # unportable_aggregate
            dom = _domain(inv.get(cid, {}))
            ops = _agg_ops(pkl.get(cid, {}).get("conditions", {}))
            op = ops[0] if ops else "unknown"
            aggs.append({"core_id": cid, "domains": dom, "operator": op, "description": d})
            rows.append({"core_rule_id": cid, "label": lab, "shape_iri": "",
                         "domain": dom, "port_kind": "none", "complexity_tier": "",
                         "gap_reason": f"requires uniqueness/multiplicity reasoning: {op}",
                         "rule_description": d})

    ns = sum(1 for r in rows if r["label"] == "single_domain")
    nc = sum(1 for r in rows if r["label"] == "unportable_cross_domain")
    na = sum(1 for r in rows if r["label"] == "unportable_aggregate")
    if len(rows) != 122 or ns != 85 or nc + na != 37:
        _fail(f"row counts total={len(rows)} single={ns} cross={nc} agg={na}")
    tc = Counter(r["complexity_tier"] for r in rows if r["complexity_tier"])
    for t, n in [("valueset", 7), ("existence", 2), ("aggregate", 4), ("computed", 18)]:
        if tc.get(t, 0) != n:
            _fail(f"complexity_tier '{t}' count={tc.get(t,0)}, expected {n}")
    for r in rows:
        if r["label"] != "single_domain" and not r["gap_reason"]:
            _fail(f"missing gap_reason for {r['core_rule_id']}")

    xref = Path(a.out_xref); xref.parent.mkdir(parents=True, exist_ok=True)
    # Append RECIST derivation rows from catalog
    recist_path = Path(a.recist_catalog)
    if recist_path.exists():
        with recist_path.open(encoding="utf-8", newline="") as f:
            for cat_row in csv.DictReader(f):
                sid = cat_row.get("shape_id", "")
                cid = f"RECIST_1_1_{sid}"
                rows.append({"core_rule_id": cid, "label": "recist_derivation",
                             "shape_iri": shapes.get(cid, ""),
                             "domain": "RS", "port_kind": "recist_sparql",
                             "complexity_tier": "", "gap_reason": "",
                             "rule_description": cat_row.get("name", "")})
    with xref.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    _write_gap(Path(a.out_gap), a.date, tiers, aggs, ns, nc, na, tc)


if __name__ == "__main__":
    main()
