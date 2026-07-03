"""E2 robustness check: do the A07/A20 *detectors* transfer to real CA012
structure once the injector is made schedule-aware?

The headline E2 (``run_e2_real_data``) uses the validated ``bench.mutations``
injectors and reports CA012 16/18 — A07/A20 miss there because those two
injectors are benchmark-shaped (dense-schedule / single-RS-row; see
``bench.variant_injectors``). This check re-injects the *same* contradictions
with the schedule-aware variants on a per-subject subgraph and applies the
identical rigorous detection criterion (the archetype's own shape fires on the
injected subject but not on its clean baseline). It does **not** alter the
validated benchmark, the Track-B 20/20 result, or the headline real-data recall.

Usage::

    PYTHONIOENCODING=ascii:replace uv run python -m scripts.run_e2_variant_check \
        --src data/real_sdtm/ca012 --backend oxigraph --out eval/real_data_e2_ca012_variant.json
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from bench.injector import Injector
from bench.variant_injectors import VARIANT_MUTATIONS
from scripts.run_e2_real_data import _build_graph, _candidates, _detect, _subject_frames

logger = logging.getLogger(__name__)


def _inject_detect(frames, aid, subj, backend) -> bool:
    """True iff the variant injection makes Ai newly fire on the injected subject."""
    mini = _subject_frames(frames, subj)
    clean, _ = _detect(_build_graph(mini), backend)
    clean_arch = {a for (a, s) in clean if s == subj}
    mut_frames, _meta = VARIANT_MUTATIONS[aid]({k: v.copy() for k, v in mini.items()}, subj)
    mut, _ = _detect(_build_graph(mut_frames), backend)
    mut_arch = {a for (a, s) in mut if s == subj}
    return aid in (mut_arch - clean_arch)


def run(src: str, backend: str, out: Path, candidates: int = 10) -> dict:
    frames = Injector(source_dirs=[src])._load_all()
    clean_full, _ = _detect(_build_graph(frames), backend)
    results = {}
    for aid in sorted(VARIANT_MUTATIONS):
        detected, tried = 0, 0
        usubjid = ""
        for c in _candidates(frames, aid, clean_full, candidates):
            tried += 1
            try:
                if _inject_detect(frames, aid, c, backend):
                    detected += 1
                    usubjid = usubjid or c
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s/%s: %s", aid, c, exc)
        results[aid] = {"status": "detected" if detected else "missed",
                        "candidates_tried": tried, "candidates_detected": detected,
                        "usubjid": usubjid}
        logger.info("%s: %s (%d/%d)", aid, results[aid]["status"], detected, tried)
    report = {"src": src, "backend": backend, "injector": "schedule_aware_variant",
              "note": "robustness check; validated bench.mutations + headline recall unchanged",
              "archetypes": results}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("->", out)
    return report


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="A07/A20 schedule-aware variant E2 robustness check.")
    ap.add_argument("--src", default="data/real_sdtm/ca012")
    ap.add_argument("--backend", choices=["pyshacl", "oxigraph"], default="oxigraph")
    ap.add_argument("--candidates", type=int, default=10)
    ap.add_argument("--out", default="eval/real_data_e2_ca012_variant.json")
    a = ap.parse_args(argv)
    run(a.src, a.backend, Path(a.out), a.candidates)


if __name__ == "__main__":
    main()
