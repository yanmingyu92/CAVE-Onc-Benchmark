"""Tamper-evident audit store backed by SQLite WAL with a Merkle hash chain."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Literal

from audit.trace_schema import TraceEntry, compute_entry_hash

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS traces (
    flag_id       TEXT PRIMARY KEY,
    timestamp     TEXT NOT NULL,
    subject       TEXT NOT NULL,
    visit         TEXT,
    layer         TEXT NOT NULL,
    archetype     TEXT NOT NULL,
    severity      TEXT NOT NULL,
    evidence_path TEXT NOT NULL,
    shacl_shape   TEXT,
    dag_node      TEXT,
    agent_trace   TEXT,
    core_rule_xref TEXT NOT NULL,
    reviewer_label TEXT,
    prev_hash     TEXT NOT NULL,
    entry_hash    TEXT NOT NULL
)
"""

_INSERT = """\
INSERT INTO traces (flag_id, timestamp, subject, visit, layer, archetype,
    severity, evidence_path, shacl_shape, dag_node, agent_trace,
    core_rule_xref, reviewer_label, prev_hash, entry_hash)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _row_to_entry(row: tuple) -> TraceEntry:
    """Convert a DB row tuple to a TraceEntry model."""
    return TraceEntry(
        flag_id=row[0],
        timestamp=row[1],
        subject=row[2],
        visit=row[3],
        layer=row[4],
        archetype=row[5],
        severity=row[6],
        evidence_path=json.loads(row[7]),
        shacl_shape=row[8],
        dag_node=row[9],
        agent_trace=json.loads(row[10]) if row[10] else None,
        core_rule_xref=json.loads(row[11]),
        reviewer_label=row[12],
        prev_hash=row[13],
        entry_hash=row[14],
    )


class AuditStore:
    """Append-only SQLite audit store with Merkle-chain integrity."""

    def __init__(self, db_path: str | Path = "audit/audit.db") -> None:
        self._path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # -- context manager --------------------------------------------------
    def __enter__(self) -> AuditStore:
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- write ------------------------------------------------------------
    def append(self, entry: TraceEntry) -> None:
        """Insert one trace entry.  Raises ``IntegrityError`` on duplicate flag_id."""
        assert self._conn is not None, "AuditStore must be used as context manager"
        self._conn.execute(
            _INSERT,
            (
                str(entry.flag_id),
                entry.timestamp.isoformat(),
                entry.subject,
                entry.visit,
                entry.layer,
                entry.archetype,
                entry.severity,
                json.dumps(entry.evidence_path, default=str),
                entry.shacl_shape,
                entry.dag_node,
                json.dumps(entry.agent_trace, default=str) if entry.agent_trace else None,
                json.dumps(entry.core_rule_xref, default=str),
                entry.reviewer_label,
                entry.prev_hash,
                entry.entry_hash,
            ),
        )
        self._conn.commit()

    # -- read -------------------------------------------------------------
    def get_chain_tip(self) -> str:
        """Return ``entry_hash`` of the most recent entry, or ``'genesis'``."""
        assert self._conn is not None
        cur = self._conn.execute("SELECT entry_hash FROM traces ORDER BY rowid DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else "genesis"

    def count(self) -> int:
        assert self._conn is not None
        cur = self._conn.execute("SELECT COUNT(*) FROM traces")
        return cur.fetchone()[0]

    def verify_chain(self) -> bool:
        """Walk the chain; return ``True`` iff every hash linkage is intact."""
        assert self._conn is not None
        cur = self._conn.execute("SELECT * FROM traces ORDER BY rowid ASC")
        rows = cur.fetchall()
        prev_hash = "genesis"
        for row in rows:
            entry = _row_to_entry(row)
            if entry.prev_hash != prev_hash:
                return False
            recomputed = compute_entry_hash(entry)
            if entry.entry_hash != recomputed:
                return False
            prev_hash = entry.entry_hash
        return True

    def query_by_subject(self, subject: str) -> list[TraceEntry]:
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT * FROM traces WHERE subject = ? ORDER BY rowid ASC",
            (subject,),
        )
        return [_row_to_entry(r) for r in cur.fetchall()]

    def query_by_archetype(self, archetype: str) -> list[TraceEntry]:
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT * FROM traces WHERE archetype = ? ORDER BY rowid ASC",
            (archetype,),
        )
        return [_row_to_entry(r) for r in cur.fetchall()]
