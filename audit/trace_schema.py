"""TraceEntry Pydantic model and helpers for the tamper-evident audit store."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TraceEntry(BaseModel):
    """Single audit-trace entry with Merkle-chain linkage (proposal §6)."""

    flag_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    subject: str
    visit: str | None = None
    layer: Literal["L1", "L2", "L3"]
    archetype: str
    severity: Literal["info", "warning", "violation"]
    evidence_path: list[dict] = Field(default_factory=list)
    shacl_shape: str | None = None
    dag_node: str | None = None
    agent_trace: dict | None = None
    core_rule_xref: list[str] = Field(default_factory=list)
    reviewer_label: Literal["TP", "FP", "pending"] | None = None
    prev_hash: str
    entry_hash: str = ""


def compute_entry_hash(entry: TraceEntry) -> str:
    """Deterministic SHA-256 of the entry excluding ``entry_hash`` itself."""
    dump = entry.model_dump()
    dump.pop("entry_hash", None)
    canonical = json.dumps(dump, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_trace_entry(
    *,
    subject: str,
    layer: Literal["L1", "L2", "L3"],
    archetype: str,
    severity: Literal["info", "warning", "violation"],
    prev_hash: str,
    visit: str | None = None,
    evidence_path: list[dict] | None = None,
    shacl_shape: str | None = None,
    dag_node: str | None = None,
    agent_trace: dict | None = None,
    core_rule_xref: list[str] | None = None,
    reviewer_label: Literal["TP", "FP", "pending"] | None = None,
) -> TraceEntry:
    """Factory: auto-generates ``flag_id``, ``timestamp``, and ``entry_hash``."""
    entry = TraceEntry(
        subject=subject,
        visit=visit,
        layer=layer,
        archetype=archetype,
        severity=severity,
        evidence_path=evidence_path or [],
        shacl_shape=shacl_shape,
        dag_node=dag_node,
        agent_trace=agent_trace,
        core_rule_xref=core_rule_xref or [],
        reviewer_label=reviewer_label,
        prev_hash=prev_hash,
    )
    entry.entry_hash = compute_entry_hash(entry)
    return entry
