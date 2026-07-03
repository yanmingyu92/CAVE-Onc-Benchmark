"""Held-out contradiction archetypes (H01-H05) for generalization testing.

Item D (R1-2, R1-1): these archetypes are authored to probe patterns the 18
existing archetype SHACL-SPARQL shapes were NOT designed for. They are run
against the EXISTING L1 shapes + L3 agent with NO new shape authoring, to
measure whether the constructed shapes generalize beyond the patterns they were
built to detect (a partial pass is the honest, expected outcome and directly
rebuts the "tailored rule-engine" critique).

Each function takes ``dict[str, pd.DataFrame]`` and returns ``(frames, meta)``,
mirroring bench/mutations.py. Mutations are defensive about missing columns.
"""
from __future__ import annotations

import pandas as pd

from bench.mutations import _pick, _shift_date, mutate_A01, mutate_A02


def _ensure_col(df: pd.DataFrame, col: str, default: str = "") -> pd.DataFrame:
    if col not in df.columns:
        df[col] = default
    return df


# -- H01: multi-archetype co-occurrence (answers R2-3 interaction) -------------

def mutate_H01(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """H01: two contradictions (A01 SLD/PD + A02 new-lesion) in the SAME subject.

    Tests whether co-occurring contradictions are each still detected, or whether
    interaction masks one of them — the multi-archetype interaction case
    Reviewer #2 raised. Reuses the frozen A01/A02 mutations on one subject.
    """
    s = _pick(frames, "RS", usubjid)
    frames, _ = mutate_A01(frames, usubjid=s)
    frames, _ = mutate_A02(frames, usubjid=s)
    return frames, {"archetype": "H01", "usubjid": s,
                    "description": "A01 + A02 co-injected in one subject (interaction)"}


# -- H02: informed consent dated AFTER first exposure --------------------------

def mutate_H02(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """H02: DM.RFICDTC (informed consent) AFTER earliest EX.EXSTDTC.

    A genuine regulatory contradiction (consent must precede exposure) with NO
    corresponding shape among A01-A20 (those check RFXSTDTC/RFXENDTC derivation
    match, not consent ordering). Expected: MISS by existing shapes.
    """
    dm, ex = frames["DM"].copy(), frames.get("EX")
    s = _pick(frames, "DM", usubjid)
    dm = _ensure_col(dm, "RFICDTC")
    first_ex = ""
    if ex is not None and not ex.empty:
        exs = ex[(ex["USUBJID"] == s) & (ex.get("EXSTDTC", "").astype(str) != "")]
        if not exs.empty:
            first_ex = str(sorted(exs["EXSTDTC"].astype(str))[0])[:10]
    if not first_ex:
        first_ex = "2014-01-01"
    dm.loc[dm["USUBJID"] == s, "RFICDTC"] = _shift_date(first_ex, 14)  # consent 14d AFTER exposure
    frames["DM"] = dm
    return frames, {"archetype": "H02", "usubjid": s,
                    "description": "RFICDTC 14d after first EXSTDTC (consent after exposure)"}


# -- H03: target lesion reappears after CR without RS escalation ----------------

def mutate_H03(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """H03: RS=CR at a visit, but a target lesion is still measurable (LDIAM>0)
    at the same/later visit with no RS->PD. Novel TR+RS consistency pattern not
    covered by A01 (SLD decrease + PD). Expected: MISS or partial.
    """
    rs, tr = frames["RS"].copy(), frames["TR"].copy()
    s = _pick(frames, "RS", usubjid)
    vn = rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
    rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "RSORRES"] = "CR"
    # ensure a measurable target lesion at that visit
    mask = (tr["USUBJID"] == s) & (tr["VISITNUM"] == vn) & (tr["TRTESTCD"] == "LDIAM")
    if mask.any():
        tr.loc[mask, "TRSTRESN"] = 25.0  # measurable disease despite CR
    frames["RS"], frames["TR"] = rs, tr
    return frames, {"archetype": "H03", "usubjid": s,
                    "description": "RS=CR but target LDIAM=25mm measurable at same visit"}


# -- H04: value-perturbation of A06 (UNEQUIVOCAL PROGRESSION + RS=PR) -----------

def mutate_H04(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """H04: non-target UNEQUIVOCAL PROGRESSION but RSORRES='PR' (not 'SD').

    Perturbs A06's value (A06 shape filters RSORRES='SD'; A18 filters !='PD').
    Tests robustness to a value change. Expected: DETECT via the A18 shape.
    """
    rs, tr = frames["RS"].copy(), frames["TR"].copy()
    s = _pick(frames, "RS", usubjid)
    vn = rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
    rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "RSORRES"] = "PR"
    nt = (tr["USUBJID"] == s) & (tr["VISITNUM"] == vn) & (tr["TRTESTCD"] == "TUMSTATE")
    if "TRGRPID" in tr.columns:
        nt &= (tr["TRGRPID"] == "NON-TARGET")
    if nt.any():
        tr.loc[nt, "TRORRES"] = "UNEQUIVOCAL PROGRESSION"
    else:  # create a non-target progression row if none exists
        row = tr.iloc[-1].copy()
        row.update({"USUBJID": s, "VISITNUM": vn, "TRTESTCD": "TUMSTATE",
                    "TRORRES": "UNEQUIVOCAL PROGRESSION"})
        if "TRGRPID" in tr.columns:
            row["TRGRPID"] = "NON-TARGET"
        tr = pd.concat([tr, pd.DataFrame([row])], ignore_index=True)
    frames["RS"], frames["TR"] = rs, tr
    return frames, {"archetype": "H04", "usubjid": s,
                    "description": "Non-target UNEQUIVOCAL PROGRESSION but RS=PR (A06 value-perturbed)"}


# -- H05: exposed but not arm-assigned (inverse of A14) ------------------------

def mutate_H05(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """H05: subject has EX records but DM.ARMCD/ACTARMCD blanked.

    Inverse of A14 (assigned-but-no-EX). 'Exposed-but-not-assigned' has no shape
    among A01-A20. Expected: MISS by existing shapes.
    """
    dm = frames["DM"].copy()
    ex = frames.get("EX")
    # pick a subject that HAS exposure
    s = ""
    if ex is not None and not ex.empty:
        exposed = set(ex["USUBJID"].unique())
        for cand in dm["USUBJID"]:
            if cand in exposed:
                s = cand
                break
    s = s or _pick(frames, "DM", usubjid)
    for col in ("ARMCD", "ACTARMCD"):
        if col in dm.columns:
            dm.loc[dm["USUBJID"] == s, col] = ""
    frames["DM"] = dm
    return frames, {"archetype": "H05", "usubjid": s,
                    "description": "EX present but ARMCD/ACTARMCD blanked (exposed, not assigned)"}


HELDOUT_MUTATIONS = {
    "H01": mutate_H01, "H02": mutate_H02, "H03": mutate_H03,
    "H04": mutate_H04, "H05": mutate_H05,
}
