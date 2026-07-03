# audit/ — Audit Trail Layer

Tamper-evident audit trail foundation compatible with 21 CFR Part 11.

## Scope (T5.3)
- `TraceEntry` Pydantic schema (proposal §6)
- SQLite WAL storage
- Merkle hash chain for tamper-evidence
- Per-entry fields: layer, archetype_id, USUBJID, timestamp, verdict, evidence, core_rule_xref
