"""Tests for audit/trace_schema.py and audit/store.py (T5.3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from audit.store import AuditStore
from audit.trace_schema import TraceEntry, compute_entry_hash, create_trace_entry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(subject: str = "SUBJ001", archetype: str = "A01", prev_hash: str = "genesis", **kw):
    kw.setdefault("prev_hash", prev_hash)
    kw.setdefault("subject", subject)
    kw.setdefault("archetype", archetype)
    return create_trace_entry(
        layer="L1",
        severity="warning",
        **kw,
    )


@pytest.fixture()
def store(tmp_path):
    """Provide a temporary AuditStore opened as context manager."""
    db = tmp_path / "test.db"
    s = AuditStore(db)
    with s:
        yield s


# ---------------------------------------------------------------------------
# 1. Schema
# ---------------------------------------------------------------------------

def test_trace_entry_schema():
    """TraceEntry can be constructed with all 14 fields."""
    entry = _make_entry()
    dumped = entry.model_dump()
    expected_fields = {
        "flag_id", "timestamp", "subject", "visit", "layer", "archetype",
        "severity", "evidence_path", "shacl_shape", "dag_node",
        "agent_trace", "core_rule_xref", "reviewer_label",
        "prev_hash", "entry_hash",
    }
    assert set(dumped.keys()) == expected_fields
    assert len(expected_fields) == len(dumped) == 15  # 14 spec + entry_hash


# ---------------------------------------------------------------------------
# 2. Hash determinism
# ---------------------------------------------------------------------------

def test_entry_hash_determinism():
    """Same inputs produce the same entry_hash across two calls."""
    e1 = _make_entry(subject="SUBJ002", archetype="A03")
    e2 = TraceEntry(**{**e1.model_dump(), "entry_hash": ""})
    assert compute_entry_hash(e1) == compute_entry_hash(e2)


# ---------------------------------------------------------------------------
# 3. Merkle chain integrity
# ---------------------------------------------------------------------------

def test_merkle_chain_integrity(store):
    """Append 5 entries and verify the chain is intact."""
    tip = "genesis"
    for i in range(5):
        entry = _make_entry(subject=f"S{i}", prev_hash=tip)
        store.append(entry)
        tip = entry.entry_hash
    assert store.count() == 5
    assert store.verify_chain() is True
    assert store.get_chain_tip() == tip


# ---------------------------------------------------------------------------
# 4. Tamper detection
# ---------------------------------------------------------------------------

def test_merkle_chain_tamper_detection(store, tmp_path):
    """Corrupt one entry_hash in the DB and detect tampering."""
    for i in range(3):
        tip = store.get_chain_tip()
        entry = _make_entry(subject=f"S{i}", prev_hash=tip)
        store.append(entry)

    # Manually corrupt the middle entry's hash
    store._conn.execute(
        "UPDATE traces SET entry_hash = 'deadbeef' WHERE subject = 'S1'"
    )
    store._conn.commit()

    assert store.verify_chain() is False


# ---------------------------------------------------------------------------
# 5. Query by subject
# ---------------------------------------------------------------------------

def test_query_by_subject(store):
    """query_by_subject returns only entries matching the USUBJID."""
    for subj in ("A", "B", "A", "B", "A"):
        tip = store.get_chain_tip()
        store.append(_make_entry(subject=subj, prev_hash=tip))

    results = store.query_by_subject("A")
    assert len(results) == 3
    assert all(e.subject == "A" for e in results)


# ---------------------------------------------------------------------------
# 6. Query by archetype
# ---------------------------------------------------------------------------

def test_query_by_archetype(store):
    """query_by_archetype returns only entries matching the archetype."""
    for arc in ("A01", "A02", "A01", "A03", "A02"):
        tip = store.get_chain_tip()
        store.append(_make_entry(archetype=arc, prev_hash=tip))

    results = store.query_by_archetype("A02")
    assert len(results) == 2
    assert all(e.archetype == "A02" for e in results)
