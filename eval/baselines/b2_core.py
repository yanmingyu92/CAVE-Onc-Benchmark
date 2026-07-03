"""B2 CORE baseline — parses pre-generated CORE CLI JSON into FlagRecords.

Reads ``eval/core_<stem>_raw.json`` where *stem* matches ``data_dir.name``.
Filters ``Issue_Details`` to oncology datasets (dm/ex/tu/tr/rs).
Falls back to ``run_cli`` if cached JSON is absent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from eval.flag_schema import FlagRecord, FlagSet

logger = logging.getLogger(__name__)

_ONCOLOGY_DATASETS = frozenset({"dm.xpt", "ex.xpt", "tu.xpt", "tr.xpt", "rs.xpt"})


def _find_cache(data_dir: Path) -> Path | None:
    """Locate ``eval/core_<stem>_raw.json`` matching *data_dir.name*."""
    stem = data_dir.name
    candidate = Path("eval") / f"core_{stem}_raw.json"
    if candidate.is_file():
        return candidate
    return None


def _parse_flags(raw: dict) -> list[FlagRecord]:
    """Filter *Issue_Details* to oncology and convert to FlagRecords."""
    flags: list[FlagRecord] = []
    for row in raw.get("Issue_Details", []):
        dataset = row.get("dataset", "")
        if dataset.lower() not in _ONCOLOGY_DATASETS:
            continue
        usubjid = row.get("USUBJID", "") or ""
        core_id = row.get("core_id", "unknown")
        message = row.get("message", "")
        domain = dataset.split(".")[0].upper()
        flags.append(FlagRecord(
            subject=usubjid,
            archetype=None,
            rule_id=core_id,
            domain=domain,
            severity="violation",
            message=message,
            source="B2_CORE",
        ))
    return flags


def run_cli(data_dir: Path) -> FlagSet:
    """Invoke CORE CLI — placeholder for future implementation."""
    raise NotImplementedError(
        "B2 CORE requires cached JSON. Run CORE CLI and save to "
        "eval/core_<stem>_raw.json first."
    )


def run(data_dir: Path) -> FlagSet:
    """Parse cached CORE JSON for *data_dir* into a FlagSet."""
    cache = _find_cache(data_dir)
    if cache is None:
        return run_cli(data_dir)
    raw = json.loads(cache.read_text(encoding="utf-8"))
    flags = _parse_flags(raw)
    logger.info("B2 CORE: %d oncology flags from %s", len(flags), cache)
    return FlagSet(flags)
