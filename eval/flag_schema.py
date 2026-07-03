"""Common flag schema for normalising outputs across validation baselines."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field


Source = Literal["B1_P21", "B2_CORE", "B3_L1", "B4_IFESD", "B5_RAG", "CAVE"]


class FlagRecord(BaseModel):
    """Single normalised validation flag (proposal §4)."""

    subject: str
    archetype: str | None = None
    rule_id: str
    domain: str
    severity: str
    message: str
    source: Source


class FlagSet:
    """Ordered collection of FlagRecords with comparison helpers."""

    def __init__(self, flags: list[FlagRecord] | None = None) -> None:
        self.flags: list[FlagRecord] = flags or []

    def __len__(self) -> int:
        return len(self.flags)

    def __iter__(self):
        return iter(self.flags)

    # -- helpers ---------------------------------------------------------------

    def _pairs(self) -> set[tuple[str, str]]:
        return {(f.subject, f.rule_id) for f in self.flags}

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([f.model_dump() for f in self.flags])

    def jaccard(self, other: FlagSet) -> float:
        a, b = self._pairs(), other._pairs()
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def per_rule_recall(self, gold: FlagSet) -> dict[str, float]:
        gold_by_rule: dict[str, set[tuple[str, str]]] = {}
        for f in gold.flags:
            gold_by_rule.setdefault(f.rule_id, set()).add((f.subject, f.rule_id))
        pred_by_rule: dict[str, set[tuple[str, str]]] = {}
        for f in self.flags:
            pred_by_rule.setdefault(f.rule_id, set()).add((f.subject, f.rule_id))
        out: dict[str, float] = {}
        for rule, gold_pairs in gold_by_rule.items():
            pred_pairs = pred_by_rule.get(rule, set())
            out[rule] = len(pred_pairs & gold_pairs) / len(gold_pairs) if gold_pairs else 0.0
        return out

    def cave_only(self, core_flags: FlagSet) -> FlagSet:
        core_pairs = core_flags._pairs()
        return FlagSet([f for f in self.flags if (f.subject, f.rule_id) not in core_pairs])
