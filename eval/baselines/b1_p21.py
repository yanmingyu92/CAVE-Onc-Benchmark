"""B1 Pinnacle 21 baseline.

Status (2026-07-02)
-------------------
The *branded* Pinnacle 21 Community FDA production engine was run empirically on the
Track B corpus (same ``bench/core_lean`` corpora as the CORE baseline), via
``scripts/run_p21_fda_baseline.py`` (engine ``FDA 2405.2``, SDTMIG 3.4). Result in
``eval/p21_fda_benchmark.json``:

    P21 FDA detects 6/20 archetypes DIRECTLY — all among the CORE-seeded structural
    class (A08-A17); **0/10 of the non-CORE cross-domain RECIST contradictions**
    (CAVE 10/10 there).

This is the industry-standard production engine (not just the open CORE engine): both
the open CORE engine (``eval/core_p21_benchmark.json``, 8/20 direct, 0/10 non-CORE) and
the branded FDA engine (6/20 direct, 0/10 non-CORE) are domain-scoped structural
validators, so **neither catches any of the ten non-CORE cross-domain contradictions**
CAVE targets. The two engines differ only on which CORE-seeded structural checks they
ship (P21 FDA lacks the reference-date-aggregation and RACE=MULTIPLE rules CORE has, but
catches the missing-EX check CORE misses) -- a portability difference, not novelty.

Reproduce::

    python -m scripts.run_p21_fda_baseline all   # runs the P21 CLI + adjudicates
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.flag_schema import FlagSet

# Empirical baselines on the Track B corpus.
_CORE_P21_RESULT = Path("eval/core_p21_benchmark.json")   # open CORE engine
_P21_FDA_RESULT = Path("eval/p21_fda_benchmark.json")     # branded FDA production engine


def run(data_dir: Path) -> FlagSet:
    """In-process FlagSet interface — intentionally a stub (like ``b2_core.run``).

    P21 is an external Java CLI that emits an ``.xlsx`` report, not an in-process
    FlagSet over a data dir, so the empirical run is corpus-level: see
    ``scripts/run_p21_fda_baseline.py`` and ``eval/p21_fda_benchmark.json``
    (FDA 2405.2: 6/20 direct, 0/10 on the non-CORE cross-domain class). Use
    ``fda_result()`` to load it.
    """
    raise NotImplementedError(
        "Pinnacle 21 FDA engine runs via the external CLI; the empirical Track B "
        "result is in eval/p21_fda_benchmark.json — see scripts/run_p21_fda_baseline.py "
        "and b1_p21.fda_result()."
    )


def fda_result() -> dict:
    """Return the empirical branded Pinnacle 21 FDA-engine result on Track B."""
    if not _P21_FDA_RESULT.is_file():
        raise FileNotFoundError(
            f"{_P21_FDA_RESULT} missing — run `python -m scripts.run_p21_fda_baseline all`."
        )
    return json.loads(_P21_FDA_RESULT.read_text(encoding="utf-8"))


def core_ceiling() -> dict:
    """Return the empirical open-CORE-engine result on Track B."""
    if not _CORE_P21_RESULT.is_file():
        raise FileNotFoundError(
            f"{_CORE_P21_RESULT} missing — run scripts/run_core_p21_baseline.sh first."
        )
    return json.loads(_CORE_P21_RESULT.read_text(encoding="utf-8"))
