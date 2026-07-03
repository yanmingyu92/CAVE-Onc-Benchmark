"""Unit tests for the schedule-aware A07/A20 variant injectors (Item E, T3).

Pure-synthetic (no PDS data): assert that each variant produces the RS structure
its archetype shape keys on, on a sparse/multi-row schedule where the validated
``bench.mutations`` injectors do not transfer.
"""
from __future__ import annotations

import pandas as pd

from bench.variant_injectors import variant_mutate_A07, variant_mutate_A20


def _sparse_multirow_rs() -> dict:
    """One subject, two far-apart visits, multi-row RS (target + overall per visit)."""
    rows = []
    for vn, dt in [(1.0, "2010-01-01"), (5.0, "2010-04-01")]:
        rows.append({"USUBJID": "S1", "VISITNUM": vn, "RSTESTCD": "OVRESP",
                     "RSORRES": "SD", "RSSTRESC": "SD", "RSDTC": dt, "RSSEQ": len(rows) + 1})
        rows.append({"USUBJID": "S1", "VISITNUM": vn, "RSTESTCD": "OVRLRESP",
                     "RSORRES": "SD", "RSSTRESC": "SD", "RSDTC": dt, "RSSEQ": len(rows) + 1})
    return {"RS": pd.DataFrame(rows)}


def test_variant_a07_creates_unconfirmed_pr():
    frames, meta = variant_mutate_A07(_sparse_multirow_rs(), "S1")
    ov = frames["RS"]
    ov = ov[ov["RSTESTCD"] == "OVRLRESP"].sort_values("VISITNUM")
    assert ov.iloc[0]["RSORRES"] == "PR", "earliest overall visit should be PR"
    # No later overall PR/CR -> A07 (PR without confirmation) is satisfiable.
    later = ov.iloc[1:]
    assert not later["RSORRES"].isin(["PR", "CR"]).any()
    assert "PR" in meta["description"]


def test_variant_a20_appends_overall_icpd():
    base = _sparse_multirow_rs()
    n_before = len(base["RS"])
    frames, meta = variant_mutate_A20(base, "S1")
    rs = frames["RS"]
    assert len(rs) == n_before + 1
    icpd = rs[rs["RSORRES"] == "iCPD"]
    assert len(icpd) == 1
    # Critically the appended row carries the OVRLRESP test code (the A20 shape key),
    # not the subject's first-row target test code.
    assert icpd.iloc[0]["RSTESTCD"] == "OVRLRESP"
    assert icpd.iloc[0]["VISITNUM"] == frames["RS"]["VISITNUM"].max()


def test_variant_a07_noop_on_single_visit():
    rs = pd.DataFrame([{"USUBJID": "S1", "VISITNUM": 1.0, "RSTESTCD": "OVRLRESP",
                        "RSORRES": "SD", "RSSTRESC": "SD", "RSDTC": "2010-01-01", "RSSEQ": 1}])
    frames, meta = variant_mutate_A07({"RS": rs}, "S1")
    assert "skipped" in meta["description"]
