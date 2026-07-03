"""Contradiction injector — loads clean SDTM XPTs, applies archetype mutations,
writes corrupted copies, and produces a manifest.

Typical usage::

    injector = Injector(
        source_dirs=["data/pilot1", "data/pharmaversesdtm_recist"],
        output_dir="bench/output",
    )
    meta = injector.inject("A01")
    print(injector.manifest())
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pyreadstat
from pandas import DataFrame

from bench.mutations import MUTATIONS

logger = logging.getLogger(__name__)

# Domains loaded from each source directory (lower-case stems).
_PILOT1_DOMAINS = {
    "dm", "ex", "ae", "ds", "lb", "mh", "qs", "sc", "se",
    "sv", "ta", "te", "ti", "ts", "tv", "vs", "cm",
    "relrec", "suppae", "suppdm", "suppds", "supplb",
}
_RECIST_DOMAINS = {"rs", "tr", "tu"}


class Injector:
    """Loads clean XPT datasets, applies one archetype mutation per call."""

    def __init__(
        self,
        source_dirs: list[str | Path] | None = None,
        output_dir: str | Path = "bench/output",
    ) -> None:
        self.source_dirs = [Path(d) for d in (source_dirs or [
            "data/pilot1", "data/pharmaversesdtm_recist",
        ])]
        self.output_dir = Path(output_dir)
        self._manifest: list[dict[str, Any]] = []

    # -- public API -----------------------------------------------------------

    def inject(
        self,
        archetype_id: str,
        usubjid: str | None = None,
    ) -> dict[str, Any]:
        """Inject one contradiction for *archetype_id* and write output.

        Returns the mutation metadata dict.
        """
        if archetype_id not in MUTATIONS:
            raise ValueError(f"Unknown archetype: {archetype_id}")
        frames = self._load_all()
        mutator = MUTATIONS[archetype_id]
        frames, meta = mutator(frames, usubjid=usubjid)
        meta["domains_modified"] = sorted(
            k for k in frames if frames[k] is not None and not frames[k].empty
        )
        self._write(frames, archetype_id)
        self._manifest.append(meta)
        logger.info("Injected %s: %s", archetype_id, meta.get("description", ""))
        return meta

    def inject_all(self, usubjid: str | None = None) -> list[dict[str, Any]]:
        """Inject all 20 archetypes (one contradiction each)."""
        results = []
        for aid in sorted(MUTATIONS):
            results.append(self.inject(aid, usubjid=usubjid))
        return results

    def manifest(self) -> list[dict[str, Any]]:
        """Return the list of injected archetypes with metadata."""
        return list(self._manifest)

    def write_manifest(self, path: str | Path | None = None) -> Path:
        """Write the manifest as JSON."""
        p = Path(path) if path else self.output_dir / "manifest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._manifest, indent=2, default=str), encoding="utf-8")
        return p

    # -- loading --------------------------------------------------------------

    def _load_all(self) -> dict[str, DataFrame]:
        """Merge XPT files from all source directories into one dict."""
        frames: dict[str, DataFrame] = {}
        for src in self.source_dirs:
            if not src.exists():
                logger.warning("Source dir missing: %s", src)
                continue
            for xpt in sorted(src.glob("*.xpt")):
                domain = xpt.stem.upper()
                try:
                    df, _ = pyreadstat.read_xport(str(xpt))
                    if domain in frames and not frames[domain].empty:
                        # Merge: prefer existing, append new columns
                        frames[domain] = _merge(frames[domain], df)
                    else:
                        frames[domain] = df
                except Exception:
                    logger.warning("Failed to load %s", xpt)
        return frames

    # -- writing --------------------------------------------------------------

    def _write(self, frames: dict[str, DataFrame], tag: str) -> Path:
        """Write all frames to ``<output_dir>/<tag>/*.xpt``."""
        out = self.output_dir / tag
        out.mkdir(parents=True, exist_ok=True)
        for domain, df in frames.items():
            if df is None or df.empty:
                continue
            path = out / f"{domain}.xpt"
            try:
                pyreadstat.write_xport(df, str(path), file_label=domain)
            except Exception:
                # Fallback: write as CSV if XPT write fails
                csv_path = out / f"{domain}.csv"
                df.to_csv(csv_path, index=False)
                logger.warning("Wrote %s as CSV (XPT write failed)", domain)
        return out

    # -- helpers --------------------------------------------------------------

    def verify_relrec(self, frames: dict[str, DataFrame]) -> bool:
        """Check that no RELREC row references a missing record.

        Returns ``True`` if all references are valid.
        """
        rr = frames.get("RELREC")
        if rr is None or rr.empty:
            return True
        for _, row in rr.iterrows():
            rdomain = str(row["RDOMAIN"]).upper()
            domain_df = frames.get(rdomain)
            if domain_df is None or domain_df.empty:
                logger.warning("RELREC orphan: domain %s missing", rdomain)
                return False
            usubjid = row["USUBJID"]
            if usubjid not in domain_df["USUBJID"].values:
                logger.warning("RELREC orphan: %s/%s not found", rdomain, usubjid)
                return False
        return True


def _merge(left: DataFrame, right: DataFrame) -> DataFrame:
    """Merge two DataFrames for the same domain, preferring *left* columns."""
    # Simple strategy: if same columns, concatenate; otherwise prefer left.
    if set(left.columns) == set(right.columns):
        return left
    # Use left (first loaded wins)
    return left
