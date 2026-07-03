"""Track A (CORE regression) and Track B (CAVE novelty) metrics."""

from __future__ import annotations

from eval.flag_schema import FlagSet


def jaccard(a: FlagSet, b: FlagSet) -> float:
    """Jaccard similarity on (subject, rule_id) tuples."""
    return a.jaccard(b)


def per_rule_recall(predicted: FlagSet, gold: FlagSet) -> dict[str, float]:
    """Per-rule recall: fraction of gold flags recovered by predicted."""
    return predicted.per_rule_recall(gold)


def cave_only_catches(cave: FlagSet, core: FlagSet) -> FlagSet:
    """Flags caught by CAVE but not by CORE (novelty set)."""
    return cave.cave_only(core)


def track_a_report(l1: FlagSet, core: FlagSet) -> dict:
    """Track A regression summary — L1 vs CORE gold standard."""
    j = jaccard(l1, core)
    recall = per_rule_recall(l1, core)
    n_l1 = len(l1)
    n_core = len(core)
    pairs_l1 = l1._pairs()
    pairs_core = core._pairs()
    return {
        "track": "A",
        "jaccard": round(j, 4),
        "l1_flags": n_l1,
        "core_flags": n_core,
        "overlap": len(pairs_l1 & pairs_core),
        "pass_threshold": j >= 0.95,
        "per_rule_recall": {k: round(v, 4) for k, v in recall.items()},
    }


def track_b_report(cave: FlagSet, core: FlagSet) -> dict:
    """Track B novelty summary — CAVE-only catches beyond CORE."""
    novel = cave_only_catches(cave, core)
    return {
        "track": "B",
        "cave_flags": len(cave),
        "core_flags": len(core),
        "cave_only_count": len(novel),
        "cave_only_flags": [f.model_dump() for f in novel.flags],
        "has_novelty": len(novel) > 0,
    }
