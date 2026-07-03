"""Archetype-specific mutation functions for contradiction injection (A01–A20).

Each function takes a ``dict[str, pd.DataFrame]`` (keyed by domain) and an
optional *usubjid*, and returns ``(mutated_frames, metadata_dict)``.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def _pick(frames: dict, domain: str, usubjid: str | None = None) -> str:
    df = frames.get(domain)
    if df is None or df.empty:
        return ""
    if usubjid and usubjid in df["USUBJID"].values:
        return usubjid
    return str(df["USUBJID"].iloc[0])


def _del_relrec(frames: dict, rdomain: str, usubjid: str,
                idvar: str | None = None, idvarval=None) -> None:
    rr = frames.get("RELREC")
    if rr is None or rr.empty:
        return
    m = (rr["RDOMAIN"] == rdomain) & (rr["USUBJID"] == usubjid)
    if idvar is not None:
        m &= (rr["IDVAR"] == idvar) & (rr["IDVARVAL"].astype(str) == str(idvarval))
    frames["RELREC"] = rr[~m].reset_index(drop=True)


def _shift_date(iso: str, days: int) -> str:
    return (datetime.strptime(iso[:10], "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


# -- Mutations A01–A20 --------------------------------------------------------

def mutate_A01(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A01: SLD decrease ≥30% with RSORRES=PD."""
    rs, tr = frames["RS"].copy(), frames["TR"]
    s = _pick(frames, "RS", usubjid)
    ldiam = tr[(tr["USUBJID"] == s) & (tr["TRTESTCD"] == "LDIAM")]
    sld = ldiam.groupby("VISITNUM")["TRSTRESN"].sum().sort_index()
    bl = sld.iloc[0]
    vn = next((v for v in sld.index if v > sld.index[0] and sld[v] <= .7 * bl), sld.index[-1])
    rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "RSORRES"] = "PD"
    frames["RS"] = rs
    return frames, {"archetype": "A01", "usubjid": s,
                     "description": f"RSORRES→PD at V{int(vn)} despite ≥30% SLD decrease"}

def mutate_A02(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A02: New lesion (TU) without RS escalation."""
    rs, tu = frames["RS"], frames["TU"].copy()
    s = _pick(frames, "RS", usubjid)
    sd = rs[(rs["USUBJID"] == s) & (rs["RSORRES"] == "SD")]["VISITNUM"]
    vn = float(sd.iloc[0]) if len(sd) else rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
    nid = f"T{len(tu['TULNKID'].unique()) + 1:02d}"
    row = tu.iloc[-1].copy()
    row.update({"USUBJID": s, "VISITNUM": vn, "TULNKID": nid,
                "TUTESTCD": "TUMIDENT", "TUSEQ": len(tu) + 1})
    frames["TU"] = pd.concat([tu, pd.DataFrame([row])], ignore_index=True)
    return frames, {"archetype": "A02", "usubjid": s,
                     "description": f"New lesion {nid} at V{int(vn)}, RSORRES=SD"}

def mutate_A03(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A03: EX start after attributed AE."""
    ae = frames.get("AE", pd.DataFrame())
    if ae.empty:
        return frames, {"archetype": "A03", "usubjid": "", "description": "skipped: no AE"}
    rel = ae[ae.get("AEREL", pd.Series(dtype=str)) == "Y"]
    s = _pick(frames, "AE", usubjid) or str((rel if not rel.empty else ae).iloc[0]["USUBJID"])
    ae_dt = str((rel[rel["USUBJID"] == s] if not rel.empty else ae[ae["USUBJID"] == s]).iloc[0]["AESTDTC"])[:10]
    ex = frames.get("EX")
    if ex is not None and not ex.empty:
        ex = ex.copy()
        idx = ex[ex["USUBJID"] == s].index
        if not idx.empty:
            ex.loc[idx[0], "EXSTDTC"] = _shift_date(ae_dt, 14)
            frames["EX"] = ex
    return frames, {"archetype": "A03", "usubjid": s, "description": f"EXSTDTC→14d after AESTDTC={ae_dt}"}

def mutate_A04(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A04: Visit-window violation propagated across TR/RS/EX."""
    rs, tr = frames["RS"].copy(), frames["TR"].copy()
    s = _pick(frames, "RS", usubjid)
    vn = rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
    rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "VISITNUM"] = vn + 0.5
    tr.loc[(tr["USUBJID"] == s) & (tr["VISITNUM"] == vn), "VISITNUM"] = vn + 0.5
    frames["RS"], frames["TR"] = rs, tr
    return frames, {"archetype": "A04", "usubjid": s,
                     "description": f"TR/RS VISITNUM shifted at V{int(vn)}, EX unchanged"}

def mutate_A05(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A05: Conflicting demographics DM vs SUPPDM."""
    dm = frames["DM"]
    s = _pick(frames, "DM", usubjid)
    sex = str(dm[dm["USUBJID"] == s]["SEX"].iloc[0])
    conflict = "M" if sex == "F" else "F"
    supp = frames.get("SUPPDM", pd.DataFrame()).copy()
    row = {"STUDYID": dm[dm["USUBJID"] == s]["STUDYID"].iloc[0], "RDOMAIN": "DM",
           "USUBJID": s, "IDVAR": "", "IDVARVAL": "", "QNAM": "SEX",
           "QLABEL": "Sex", "QVAL": conflict, "QORIG": "CRF", "QEVAL": ""}
    frames["SUPPDM"] = pd.concat([supp, pd.DataFrame([row])], ignore_index=True)
    return frames, {"archetype": "A05", "usubjid": s,
                     "description": f"SUPPDM SEX={conflict} conflicts with DM SEX={sex}"}

def mutate_A06(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A06: Non-target PD with RS=SD."""
    rs, tr = frames["RS"].copy(), frames["TR"].copy()
    # Pick a subject that has NON-TARGET TUMSTATE rows in TR
    # (otherwise the mutation silently no-ops)
    nt_mask = (tr["TRTESTCD"] == "TUMSTATE")
    if "TRGRPID" in tr.columns:
        nt_mask &= (tr["TRGRPID"] == "NON-TARGET")
    ts_subjs = tr.loc[nt_mask, "USUBJID"].unique()
    rs_subjs = set(rs["USUBJID"].unique())
    candidates = [u for u in ts_subjs if u in rs_subjs]
    s = usubjid or (candidates[0] if candidates else _pick(frames, "RS"))
    vn = rs[(rs["USUBJID"] == s) & (rs["RSORRES"] == "SD")]["VISITNUM"]
    if vn.empty:
        vn = rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
        rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "RSORRES"] = "SD"
    else:
        vn = vn.iloc[0]
    nt = (tr["USUBJID"] == s) & (tr["VISITNUM"] == vn) & (tr["TRTESTCD"] == "TUMSTATE")
    if "TRGRPID" in tr.columns:
        nt &= (tr["TRGRPID"] == "NON-TARGET")
    tr.loc[nt, "TRORRES"] = "UNEQUIVOCAL PROGRESSION"
    frames["RS"], frames["TR"] = rs, tr
    return frames, {"archetype": "A06", "usubjid": s,
                     "description": f"Non-target PD at V{int(vn)} but RSORRES=SD"}

def mutate_A07(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A07: Confirmed PR without confirmation visit."""
    rs = frames["RS"].copy()
    s = _pick(frames, "RS", usubjid)
    pr = rs[(rs["USUBJID"] == s) & (rs["RSORRES"] == "PR")]
    if pr.empty:
        rs.loc[rs["USUBJID"] == s, "RSORRES"] = "PR"
        pr = rs[rs["USUBJID"] == s]
    pr_vn, pr_dt = pr["VISITNUM"].iloc[0], str(pr["RSDTC"].iloc[0])[:10]
    keep_mask = rs.apply(
        lambda r: r["USUBJID"] != s or r["VISITNUM"] <= pr_vn
        or (r["RSDTC"] and str(r["RSDTC"])[:10] <= _shift_date(pr_dt, 28)), axis=1)
    frames["RS"] = rs[keep_mask].reset_index(drop=True)
    return frames, {"archetype": "A07", "usubjid": s,
                     "description": f"PR at V{int(pr_vn)}, no confirmation within 28d"}

def mutate_A08(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A08: ARMCD not in TA valueset."""
    dm = frames["DM"].copy()
    s = _pick(frames, "DM", usubjid)
    dm.loc[dm["USUBJID"] == s, "ARMCD"] = "TRTARMX"
    frames["DM"] = dm
    return frames, {"archetype": "A08", "usubjid": s, "description": "ARMCD→TRTARMX (not in TA)"}

def mutate_A09(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A09: Assigned subject missing disposition."""
    s = _pick(frames, "DM", usubjid)
    ds = frames.get("DS", pd.DataFrame()).copy()
    if not ds.empty:
        ds = ds[ds["USUBJID"] != s].reset_index(drop=True)
        _del_relrec(frames, "DS", s)
    frames["DS"] = ds
    return frames, {"archetype": "A09", "usubjid": s,
                     "description": "DS records removed for subject with ACTARMCD"}

def mutate_A10(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A10: RFXSTDTC mismatch with earliest EXSTDTC."""
    dm = frames["DM"].copy()
    ex = frames.get("EX")
    s = _pick(frames, "DM", usubjid)
    if ex is not None and not ex.empty:
        dm.loc[dm["USUBJID"] == s, "RFXSTDTC"] = _shift_date(str(ex[ex["USUBJID"] == s]["EXSTDTC"].min())[:10], -7)
    frames["DM"] = dm
    return frames, {"archetype": "A10", "usubjid": s, "description": "RFXSTDTC shifted -7d from min EXSTDTC"}

def mutate_A11(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A11: RFXENDTC mismatch with latest EXENDTC."""
    dm = frames["DM"].copy()
    ex = frames.get("EX")
    s = _pick(frames, "DM", usubjid)
    if ex is not None and not ex.empty:
        dm.loc[dm["USUBJID"] == s, "RFXENDTC"] = _shift_date(str(ex[ex["USUBJID"] == s]["EXENDTC"].max())[:10], 7)
    frames["DM"] = dm
    return frames, {"archetype": "A11", "usubjid": s, "description": "RFXENDTC shifted +7d from max EXENDTC"}

def mutate_A12(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A12: Death flag without death details."""
    dm = frames["DM"].copy()
    s = _pick(frames, "DM", usubjid)
    dm.loc[dm["USUBJID"] == s, "DTHFL"] = "Y"
    frames["DM"] = dm
    return frames, {"archetype": "A12", "usubjid": s, "description": "DTHFL=Y without DD records"}

def mutate_A13(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A13: RACE=MULTIPLE without SUPPDM records."""
    dm = frames["DM"].copy()
    s = _pick(frames, "DM", usubjid)
    dm.loc[dm["USUBJID"] == s, "RACE"] = "MULTIPLE"
    frames["DM"] = dm
    return frames, {"archetype": "A13", "usubjid": s, "description": "RACE=MULTIPLE w/o SUPPDM records"}

def mutate_A14(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A14: Assigned arm but no exposure record."""
    s = _pick(frames, "DM", usubjid)
    ex = frames.get("EX", pd.DataFrame()).copy()
    if not ex.empty:
        ex = ex[ex["USUBJID"] != s].reset_index(drop=True)
        _del_relrec(frames, "EX", s)
    frames["EX"] = ex
    return frames, {"archetype": "A14", "usubjid": s,
                     "description": "EX records removed for subject with ACTARMCD"}

def mutate_A15(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A15: RFSTDTC mismatch with first EXSTDTC."""
    dm = frames["DM"].copy()
    ex = frames.get("EX")
    s = _pick(frames, "DM", usubjid)
    if ex is not None and not ex.empty:
        dm.loc[dm["USUBJID"] == s, "RFSTDTC"] = _shift_date(str(ex[ex["USUBJID"] == s]["EXSTDTC"].min())[:10], -5)
    frames["DM"] = dm
    return frames, {"archetype": "A15", "usubjid": s, "description": "RFSTDTC shifted -5d from first EXSTDTC"}

def mutate_A16(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A16: Duplicate USUBJID across studies."""
    dm = frames["DM"].copy()
    s = _pick(frames, "DM", usubjid)
    row = dm[dm["USUBJID"] == s].iloc[0].copy()
    row["STUDYID"] = "DUPLICATE_STUDY"
    frames["DM"] = pd.concat([dm, pd.DataFrame([row])], ignore_index=True)
    return frames, {"archetype": "A16", "usubjid": s, "description": "DM row dup'd with STUDYID=DUPLICATE_STUDY"}

def mutate_A17(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A17: ARMCD-ARM not one-to-one."""
    dm = frames["DM"].copy()
    s = _pick(frames, "DM", usubjid)
    armcd = str(dm[dm["USUBJID"] == s]["ARMCD"].iloc[0])
    others = dm[(dm["ARMCD"] == armcd) & (dm["USUBJID"] != s)]
    if not others.empty:
        dm.loc[others.index[0], "ARM"] = "CONFLICTING ARM NAME"
    else:
        dm.loc[dm["USUBJID"] == s, "ARM"] = "CONFLICTING ARM NAME"
    frames["DM"] = dm
    return frames, {"archetype": "A17", "usubjid": s, "description": f"ARM changed for ARMCD={armcd} → not 1:1"}

def mutate_A18(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A18: Non-target overall response misclassification."""
    rs, tr = frames["RS"].copy(), frames["TR"].copy()
    # Pick a subject that has NON-TARGET TUMSTATE rows in TR
    nt_mask = (tr["TRTESTCD"] == "TUMSTATE")
    if "TRGRPID" in tr.columns:
        nt_mask &= (tr["TRGRPID"] == "NON-TARGET")
    ts_subjs = tr.loc[nt_mask, "USUBJID"].unique()
    rs_subjs = set(rs["USUBJID"].unique())
    candidates = [u for u in ts_subjs if u in rs_subjs]
    s = usubjid or (candidates[0] if candidates else _pick(frames, "RS"))
    vn = rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
    rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "RSORRES"] = "SD"
    nt = (tr["USUBJID"] == s) & (tr["VISITNUM"] == vn) & (tr["TRTESTCD"] == "TUMSTATE")
    if "TRGRPID" in tr.columns:
        nt &= (tr["TRGRPID"] == "NON-TARGET")
    tr.loc[nt, "TRORRES"] = "UNEQUIVOCAL PROGRESSION"
    frames["RS"], frames["TR"] = rs, tr
    return frames, {"archetype": "A18", "usubjid": s,
                     "description": f"Non-target PD at V{int(vn)} but RS=SD"}

def mutate_A19(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A19: Table 7 overall response contradiction."""
    rs = frames["RS"].copy()
    s = _pick(frames, "RS", usubjid)
    vn = rs[rs["USUBJID"] == s]["VISITNUM"].iloc[0]
    rs.loc[(rs["USUBJID"] == s) & (rs["VISITNUM"] == vn), "RSORRES"] = "CR"
    frames["RS"] = rs
    return frames, {"archetype": "A19", "usubjid": s,
                     "description": f"RSORRES=CR at V{int(vn)} while target shows PR"}

def mutate_A20(frames: dict, usubjid: str | None = None) -> tuple[dict, dict]:
    """A20: iRECIST immune PD confirmation failure."""
    rs = frames["RS"].copy()
    s = _pick(frames, "RS", usubjid)
    last_vn = rs[rs["USUBJID"] == s]["VISITNUM"].max()
    row = rs[rs["USUBJID"] == s].iloc[0].copy()
    row.update({"VISITNUM": last_vn + 1, "RSORRES": "iCPD", "RSSTRESC": "iCPD",
                "RSDTC": _shift_date(str(row.get("RSDTC", "2024-01-01"))[:10], 56)})
    frames["RS"] = pd.concat([rs, pd.DataFrame([row])], ignore_index=True)
    return frames, {"archetype": "A20", "usubjid": s,
                     "description": f"iCPD at V{int(last_vn)+1}, no ≥4wk confirmation"}


MUTATIONS: dict[str, callable] = {f"A{i:02d}": globals()[f"mutate_A{i:02d}"] for i in range(1, 21)}
