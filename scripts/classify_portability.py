"""Classify 122 oncology rules by portability.

2-check cascade: $-ref -> unportable_cross_domain,
aggregate op -> unportable_aggregate, else -> single_domain.
Two-pass merge with classification_overrides.csv.
Stdlib only: pickle, csv, re, argparse, pathlib.
"""
import argparse, csv, pickle, re, sys
from pathlib import Path

DOLLAR_RE = re.compile(r"\$([a-zA-Z0-9_]+)")
AGG_OPS = frozenset({"is_not_unique_set", "is_not_unique_relationship"})
VALID_LABELS = frozenset({"single_domain", "unportable_cross_domain",
    "unportable_aggregate", "pair", "unportable_temporal"})
CLASS_COLS = ["core_id", "label", "complexity_tier",
              "dollar_refs", "aggregate_ops", "notes"]
OVER_COLS = ["core_id", "label", "complexity_tier", "rationale"]
EXPECTED = {"single_domain": 85, "unportable_cross_domain": 31,
            "unportable_aggregate": 6}


def _walk(node: object, refs: set[str], ops: set[str]) -> None:
    """Recursively collect $-references and operators from conditions tree."""
    if isinstance(node, dict):
        for k in ("target", "value", "comparator"):
            v = node.get(k)
            if isinstance(v, str):
                refs.update(DOLLAR_RE.findall(v))
        op = node.get("operator")
        if isinstance(op, str):
            ops.add(op)
        for v in node.values():
            _walk(v, refs, ops)
    elif isinstance(node, list):
        for item in node:
            _walk(item, refs, ops)


def _tier(refs: set[str]) -> str:
    """Derive complexity_tier from $-reference names (lowercased)."""
    lo = {r.lower() for r in refs}
    if any(r.startswith(("min_", "max_", "count_")) for r in lo):
        return "aggregate"
    if any(r.endswith(("_usubjid", "_usubjids")) for r in lo):
        return "existence"
    if any(r.startswith(("ta_", "tx_", "ts_")) or r == "arms_in_ta" for r in lo):
        return "valueset"
    return "computed"


def _read_ids(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r["core_id"] for r in csv.DictReader(f)]


def _read_overrides(path):
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["core_id"]: r for r in csv.DictReader(f)}


def classify(inv_csv, pkl_path, out_csv, ovr_csv):
    """Auto-classify, validate counts, merge overrides, write CSV."""
    core_ids = _read_ids(inv_csv)
    with open(pkl_path, "rb") as f:
        rules = pickle.load(f)

    # Pass 1: auto-classify
    rows, auto_counts = [], {}
    for cid in core_ids:
        refs, ops = set(), set()
        _walk(rules[cid].get("conditions", {}), refs, ops)
        label = ("unportable_cross_domain" if refs
                 else "unportable_aggregate" if ops & AGG_OPS
                 else "single_domain")
        auto_counts[label] = auto_counts.get(label, 0) + 1
        tier = _tier(refs) if label == "unportable_cross_domain" else ""
        agg = sorted(ops & AGG_OPS)
        rows.append({
            "core_id": cid, "label": label, "complexity_tier": tier,
            "dollar_refs": "|".join(sorted(refs)) if refs else "",
            "aggregate_ops": "|".join(agg) if agg else "", "notes": "",
        })

    # Validate auto-counts before overrides can mask issues
    for lbl, exp in EXPECTED.items():
        got = auto_counts.get(lbl, 0)
        if got != exp:
            print(f"COUNT MISMATCH {lbl}: expected={exp} got={got}",
                  file=sys.stderr)
            sys.exit(1)

    # Ensure overrides file exists (header-only on first run)
    if not ovr_csv.exists():
        ovr_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(ovr_csv, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=OVER_COLS).writeheader()
    # Pass 2: merge overrides
    ovr_map = _read_overrides(ovr_csv)
    for ov in ovr_map.values():
        if ov["label"] not in VALID_LABELS:
            raise ValueError(
                f"Invalid override label '{ov['label']}' for {ov['core_id']}")
    for row in rows:
        ov = ovr_map.get(row["core_id"])
        if ov:
            row["label"] = ov["label"]
            row["complexity_tier"] = ov.get("complexity_tier", "") or ""
            row["notes"] = f"OVERRIDE: {ov['rationale']}; {row['notes']}"

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CLASS_COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    p = argparse.ArgumentParser(description="Classify rule portability")
    p.add_argument("--inventory", default="gate_a/rules_inventory.csv", type=Path)
    p.add_argument("--rules-pkl", default="vendor/core/resources/cache/rules.pkl",
                   type=Path)
    p.add_argument("--out", default="gate_a/classification.csv", type=Path)
    p.add_argument("--overrides", default="gate_a/classification_overrides.csv",
                   type=Path)
    a = p.parse_args()
    rows = classify(a.inventory, a.rules_pkl, a.out, a.overrides)
    c = {}
    for r in rows:
        c[r["label"]] = c.get(r["label"], 0) + 1
    print(f"Classified {len(rows)} rules: {c}")


if __name__ == "__main__":
    main()
