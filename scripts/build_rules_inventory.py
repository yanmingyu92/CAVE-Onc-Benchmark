"""Build oncology-scoped rules inventory CSV from CORE rules.pkl.

Filters rules whose domains.Include intersects {TU, TR, RS, EX, DM}.
Stdlib only: pickle, csv, pathlib, argparse.
"""
import argparse
import csv
import pickle
import re
from pathlib import Path
from typing import Any

ONCO_TARGETS = {"TU", "TR", "RS", "EX", "DM"}

COLUMNS = [
    "core_id", "description", "sensitivity", "executability", "rule_type",
    "status", "oncology_domains", "domains_include", "domains_exclude",
    "classes_include", "standards", "use_case", "n_conditions", "n_actions",
]


def _extract(rule: dict, key: str, subkey: str | None = None) -> Any:
    """Return rule[key][subkey] or rule[key]; [] for missing list-like, '' otherwise."""
    val = rule.get(key)
    if val is None:
        return [] if subkey else ""
    if subkey is not None:
        return val.get(subkey) or [] if isinstance(val, dict) else []
    return val


def _clean(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", text).strip()


def _join_sorted(items: list) -> str:
    return ";".join(sorted(set(str(x) for x in items if x)))


def _format_standards(stds: list[dict]) -> str:
    pairs = {f"{s.get('Name','')}/{s.get('Version','')}" for s in stds
             if s.get("Name") and s.get("Version")}
    return ";".join(sorted(pairs))


def _count_leaves(node: Any) -> int:
    """Count leaf conditions (dicts with 'name' key) recursively.

    Conditions tree: {"all": [...]} or {"any": [...]} with nested groups
    or leaf dicts containing "name". Only leaves are counted.
    """
    if isinstance(node, dict):
        if "name" in node:
            return 1
        return sum(_count_leaves(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_leaves(item) for item in node)
    return 0


def build_inventory(rules_pkl: Path, out: Path) -> int:
    """Load rules.pkl, filter oncology, write CSV. Returns row count."""
    with open(rules_pkl, "rb") as f:
        rules: dict[str, dict] = pickle.load(f)

    kept: list[dict] = []
    for core_id, rule in rules.items():
        domains = rule.get("domains")
        if not isinstance(domains, dict):
            continue
        include = domains.get("Include") or []
        if not (set(include) & ONCO_TARGETS):
            continue
        onco_domains = sorted(set(include) & ONCO_TARGETS)
        exclude = domains.get("Exclude") or []
        classes_inc = _extract(rule, "classes", "Include")
        stds = _format_standards(_extract(rule, "standards") or [])
        n_cond = _count_leaves(rule.get("conditions"))
        n_act = len(rule.get("actions") or [])
        kept.append({
            "core_id": core_id,
            "description": _clean(str(rule.get("description", ""))),
            "sensitivity": rule.get("sensitivity", ""),
            "executability": rule.get("executability", ""),
            "rule_type": rule.get("rule_type", ""),
            "status": rule.get("status", ""),
            "oncology_domains": ";".join(onco_domains),
            "domains_include": _join_sorted(include),
            "domains_exclude": _join_sorted(exclude),
            "classes_include": _join_sorted(classes_inc),
            "standards": stds,
            "use_case": str(rule.get("use_case") or ""),
            "n_conditions": n_cond,
            "n_actions": n_act,
        })

    kept.sort(key=lambda r: r["core_id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(kept)
    return len(kept)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build oncology rules inventory CSV")
    parser.add_argument("--rules-pkl", default="vendor/core/resources/cache/rules.pkl", type=Path)
    parser.add_argument("--out", default="gate_a/rules_inventory.csv", type=Path)
    args = parser.parse_args()
    n = build_inventory(args.rules_pkl, args.out)
    print(f"Wrote {n} oncology rules to {args.out}")


if __name__ == "__main__":
    main()
