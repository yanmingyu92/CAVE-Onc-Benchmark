"""Schedule-aware variant injectors for the two temporal-confirmation archetypes
(A07, A20), used **only** by the real-data E2 robustness check.

Motivation (Item E, T3). On the synthetic pharmaverse benchmark the validated
``bench.mutations`` injectors detect A07 and A20, but they encode two
benchmark-shaped assumptions that fail on a real trial with a *sparse* visit
schedule (CA012 has four assessment visits) and *multi-row* RS:

* ``mutate_A07`` removes every assessment more than 28 days after an induced PR.
  On a schedule whose visits are themselves >28 days apart this deletes *all*
  later visits, so the "a later visit exists" precondition of the A07 shape can
  no longer hold and nothing fires.
* ``mutate_A20`` copies the subject's *first* RS row as the iCPD record. On the
  benchmark every RS row is ``RSTESTCD='OVRLRESP'``; on real multi-row RS the
  first row is a *target* response (``OVRESP``), so the injected iCPD carries the
  wrong test code and the A20 shape (which keys on ``OVRLRESP``) cannot match.

Both are **injector** artifacts, not detector gaps. These variants reproduce the
*same* contradictions in a schedule- and cardinality-agnostic way, so the E2
robustness check can confirm the A07/A20 *detectors* transfer to real CA012
structure. They are deliberately kept out of ``bench.mutations`` so the validated
Track-B 20/20 benchmark and the headline real-data recall (CA012 16/18 with the
validated injector) are left unchanged.
"""
from __future__ import annotations

import pandas as pd

_OVERALL = "OVRLRESP"


def _overall_rows(rs: pd.DataFrame, s: str) -> pd.DataFrame:
    return rs[(rs["USUBJID"] == s) & (rs["RSTESTCD"].astype(str).str.upper() == _OVERALL)]


def variant_mutate_A07(frames: dict, usubjid: str) -> tuple[dict, dict]:
    """A07 (PR without confirmation), schedule-agnostic.

    Set the subject's earliest overall-response visit to PR and force every
    *later* overall-response visit to a non-confirming value (SD). The A07 shape
    then fires: a PR with a later visit but no subsequent PR/CR — independent of
    the calendar spacing between visits.
    """
    rs = frames["RS"].copy()
    ov = _overall_rows(rs, usubjid).sort_values("VISITNUM")
    meta = {"archetype": "A07", "usubjid": usubjid, "description": "skipped: <2 overall visits"}
    if ov["VISITNUM"].nunique() < 2:
        frames["RS"] = rs
        return frames, meta
    visits = sorted(ov["VISITNUM"].unique())
    first, later = visits[0], visits[1:]
    rs.loc[(rs["USUBJID"] == usubjid) & (rs["VISITNUM"] == first)
           & (rs["RSTESTCD"].astype(str).str.upper() == _OVERALL),
           ["RSORRES", "RSSTRESC"]] = "PR"
    rs.loc[(rs["USUBJID"] == usubjid) & (rs["VISITNUM"].isin(later))
           & (rs["RSTESTCD"].astype(str).str.upper() == _OVERALL),
           ["RSORRES", "RSSTRESC"]] = "SD"
    frames["RS"] = rs
    meta["description"] = f"PR at V{int(first)}; later overall visits set non-PR/CR (SD)"
    return frames, meta


def variant_mutate_A20(frames: dict, usubjid: str) -> tuple[dict, dict]:
    """A20 (iCPD without confirmation), RS-cardinality-agnostic.

    Append a new overall-response (``OVRLRESP``) row carrying ``iCPD`` at the
    subject's last visit + 1, copied from a real ``OVRLRESP`` row so the test code
    is correct. With no later iCPD, the A20 shape fires regardless of how many RS
    rows the trial records per visit.
    """
    rs = frames["RS"].copy()
    ov = _overall_rows(rs, usubjid)
    meta = {"archetype": "A20", "usubjid": usubjid, "description": "skipped: no OVRLRESP row"}
    if ov.empty:
        frames["RS"] = rs
        return frames, meta
    last_vn = rs[rs["USUBJID"] == usubjid]["VISITNUM"].max()
    row = ov.sort_values("VISITNUM").iloc[-1].copy()
    row["VISITNUM"] = last_vn + 1
    row["RSORRES"] = "iCPD"
    row["RSSTRESC"] = "iCPD"
    if "RSSEQ" in rs.columns:
        mx = pd.to_numeric(rs["RSSEQ"], errors="coerce").max()
        row["RSSEQ"] = (0 if pd.isna(mx) else int(mx)) + 1
    frames["RS"] = pd.concat([rs, pd.DataFrame([row])], ignore_index=True)
    meta["description"] = f"iCPD appended at V{int(last_vn) + 1}; no confirmatory iCPD"
    return frames, meta


VARIANT_MUTATIONS = {"A07": variant_mutate_A07, "A20": variant_mutate_A20}
