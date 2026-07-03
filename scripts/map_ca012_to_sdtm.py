"""Map the CA012 metastatic-breast-cancer trial (PDS package 107) to SDTM.

Phase 4 of the Item E real-world validation (`docs/item_e_real_data_plan.md`):
the second real trial, for cross-trial external validity. CA012 is the strong
second after Synta — cleaner RECIST labels (`wclesion`/`wcresp` with explicit
target/non-target/overall responses and a derived SLD) and, crucially, it ships
**day-offset dates** (`EXAMDAY`/`DOSEDAY`/`EOSRDAY`) and a **`dose`** domain. That
lets us map an `EX` domain and real (relative) dates, so this trial can exercise
the EX-family (A10/A11/A14/A15) and date-based (A07/A20) archetypes that the
Synta RECIST package could not.

Source datasets (CA012 Data Files/*.sas7bdat), value-inspected:
  wclesion : RSUBJ_ID, VISIT_ID, LESTYPE{Target|Non Target}, LESNUM, TGTSIZE(LD mm),
             QUAN(qualitative state), LESLOC, METHOD, EXAMDAY(day offset)
  wcresp   : RSUBJ_ID, VISIT_ID, TGTRESP, NTGTRESP, ALLRESP (RECIST codes; '{---}'
             = missing), SUMTGT(SLD mm), NUMTGT, EXAMDAY
  demo     : RSUBJ_ID, AGE, ELIG_007(arm, ='B' single-arm), RACE_GEN(coded)
  dose     : RSUBJ_ID, DOSEDAY_001(start-day offset), DOSEDAY_003(stop-day offset)
  eosr     : RSUBJ_ID, EOSR_003(discontinued prematurely), EOSR_004(reason),
             EOSRDAY_001(end-of-study day offset)

Target SDTM column model (identical to the Synta mapper, consumed by the same L1
shapes + L3 agent):
  TU TR RS DM DS TA  +  EX (start/stop dates from dose)
  +  AE (solicited toxicities from `toxy`; no causality variable -> no AEREL)

Dates: source offsets are days relative to "Eligibility Verification". We anchor
day 0 at ``ANCHOR`` (arbitrary; only intervals matter — every archetype compares
relative dates) so RSDTC/EXSTDTC/EXENDTC are valid ISO dates and the 28-day
(S7/A07) and iRECIST (A20) rules become testable.

Disclosed mapping assumptions (auditable):
  * single arm 'B' (ELIG_007 is 'B' for all 227 subjects) -> ARM/ARMCD/TA.
  * SEX='F' — CA012 is a metastatic *breast cancer* trial and the CRF records
    child-bearing potential; no sex variable is provided. Disclosed.
  * RACE_GEN 1/2/9 -> WHITE / BLACK OR AFRICAN AMERICAN / UNKNOWN.
  * lesion identity = (LESTYPE, LESNUM); LESNUM is stable across visits per type
    (verified). TULNKID/TRLNKID = 'T'/'NT' + LESNUM.
  * non-target TUMSTATE derived from QUAN (disappeared->ABSENT,
    cannot-be-seen->NOT EVALUABLE, else PRESENT) — never UNEQUIVOCAL PROGRESSION,
    so E1 specificity is not spuriously tripped.

Usage::
    python -m scripts.map_ca012_to_sdtm \
        --src "data/real_oncology_data/AllProvidedFiles_107/CA012 Data Files" \
        --out data/real_sdtm/ca012
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyreadstat

# Reuse the shared graph enrichment (TRGRPID -> TRTARGETLN) from the Synta mapper.
from scripts.map_synta_to_sdtm import enrich_recist_graph  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

STUDYID_DEFAULT = "CA012"
ANCHOR = date(2010, 1, 1)  # day-0 reference for the relative day offsets
RACE_MAP = {"1": "WHITE", "2": "BLACK OR AFRICAN AMERICAN", "9": "UNKNOWN"}
RECIST_OK = {"CR", "PR", "SD", "PD", "NE", "ND"}  # '{---}' etc. are dropped


# -- helpers ------------------------------------------------------------------

def _load(src: Path, name: str) -> pd.DataFrame:
    df, _meta = pyreadstat.read_sas7bdat(str(src / f"{name}.sas7bdat"))
    return df


def _usubjid(studyid: str, rsubj) -> str:
    try:
        return f"{studyid}-{int(float(rsubj))}"
    except (TypeError, ValueError):
        return f"{studyid}-{str(rsubj).strip()}"


def _iso(offset) -> str:
    """Day offset (relative to eligibility verification) -> ISO date string."""
    if pd.isna(offset):
        return ""
    return (ANCHOR + timedelta(days=int(offset))).isoformat()


def _epoch(visitnum: float) -> str:
    return "SCREENING" if visitnum == 1 else "TREATMENT"


def _lesid(lestype: str, lesnum) -> str:
    pref = "T" if str(lestype).strip().lower().startswith("target") else "NT"
    try:
        return f"{pref}{int(float(lesnum))}"
    except (TypeError, ValueError):
        return f"{pref}{lesnum}"


def _is_target(lestype: str) -> bool:
    return str(lestype).strip().lower().startswith("target")


def _tumstate(quan: str) -> str:
    q = str(quan).strip().lower()
    if "disappeared" in q:
        return "ABSENT"
    if "cannot be seen" in q:
        return "NOT EVALUABLE"
    return "PRESENT"


def _recist(val) -> str:
    v = str(val).strip().upper()
    return v if v in RECIST_OK else ""


# -- domain builders ----------------------------------------------------------

def build_tu(wl: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """One TU row per first appearance of each (subject, lesion)."""
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    seq: dict[str, int] = {}
    les = wl.sort_values(["RSUBJ_ID", "VISIT_ID", "LESTYPE", "LESNUM"])
    for _, r in les.iterrows():
        if pd.isna(r.get("LESNUM")):
            continue
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        lesid = _lesid(r["LESTYPE"], r["LESNUM"])
        key = (uid, lesid)
        if key in seen:
            continue
        seen.add(key)
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid,
            "VISITNUM": float(r["VISIT_ID"]), "TUSEQ": seq[uid],
            "TULNKID": lesid,
            "TUCAT": "TARGET LESION" if _is_target(r["LESTYPE"]) else "NON-TARGET LESION",
            "TULOC": str(r.get("LESLOC", "") or ""),
        })
    return pd.DataFrame(rows)


def build_tr(wl: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """Target LDIAM measurements + non-target TUMSTATE rows."""
    rows: list[dict] = []
    seq: dict[str, int] = {}
    les = wl.sort_values(["RSUBJ_ID", "VISIT_ID", "LESTYPE", "LESNUM"])
    for _, r in les.iterrows():
        if pd.isna(r.get("LESNUM")):
            continue
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        vn = float(r["VISIT_ID"])
        target = _is_target(r["LESTYPE"])
        seq[uid] = seq.get(uid, 0) + 1
        base = {
            "STUDYID": studyid, "USUBJID": uid, "VISITNUM": vn,
            "TRSEQ": seq[uid], "TRLNKID": _lesid(r["LESTYPE"], r["LESNUM"]),
            "TRGRPID": "TARGET" if target else "NON-TARGET",
            "TRDTC": _iso(r.get("EXAMDAY")), "EPOCH": _epoch(vn),
        }
        if target:
            ld = r.get("TGTSIZE")
            base.update({
                "TRTESTCD": "LDIAM",
                "TRSTRESN": float(ld) if pd.notna(ld) else None,
                "TRORRES": "" if pd.isna(ld) else str(ld),
                "TRSTAT": "" if pd.notna(ld) else "NOT DONE",
            })
        else:
            base.update({"TRTESTCD": "TUMSTATE", "TRORRES": _tumstate(r.get("QUAN")),
                         "TRSTAT": ""})
        rows.append(base)
    return pd.DataFrame(rows)


def build_rs(wr: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """RS rows: target/non-target/overall response + SUMDIAM per visit."""
    rows: list[dict] = []
    seq: dict[str, int] = {}

    def add(uid, vn, dtc, cat, testcd, orres="", stresn=None):
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid, "VISITNUM": vn, "RSSEQ": seq[uid],
            "RSCAT": cat, "RSTESTCD": testcd, "RSDTC": dtc,
            "RSORRES": orres, "RSSTRESC": orres,
            "RSSTRESN": float(stresn) if stresn is not None and pd.notna(stresn) else None,
            "EPOCH": _epoch(vn),
        })

    for _, r in wr.sort_values(["RSUBJ_ID", "VISIT_ID"]).iterrows():
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        vn = float(r["VISIT_ID"])
        dtc = _iso(r.get("EXAMDAY"))
        tgt, ntgt, allr = _recist(r.get("TGTRESP")), _recist(r.get("NTGTRESP")), _recist(r.get("ALLRESP"))
        if tgt:
            add(uid, vn, dtc, "TARGET RESPONSE", "OVRESP", tgt)
        if ntgt:
            add(uid, vn, dtc, "NON-TARGET RESPONSE", "NTRGRESP", ntgt)
        if allr:
            add(uid, vn, dtc, "OVERALL RESPONSE", "OVRLRESP", allr)
        sld = r.get("SUMTGT")
        if pd.notna(sld):
            add(uid, vn, dtc, "TARGET RESPONSE", "SUMDIAM", "", sld)
    return pd.DataFrame(rows)


def build_dm(demo: pd.DataFrame, ex: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """DM with reference dates derived from EX (for the date-ref archetypes)."""
    # earliest/latest exposure per subject
    ref: dict[str, tuple[str, str]] = {}
    if not ex.empty:
        for uid, grp in ex.groupby("USUBJID"):
            starts = [s for s in grp["EXSTDTC"] if s]
            ends = [e for e in grp["EXENDTC"] if e]
            ref[uid] = (min(starts) if starts else "", max(ends) if ends else "")
    rows: list[dict] = []
    for _, r in demo.drop_duplicates(subset=["RSUBJ_ID"]).iterrows():
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        arm = str(r.get("ELIG_007", "") or "").strip() or "B"
        rfst, rfen = ref.get(uid, ("", ""))
        rows.append({
            "STUDYID": studyid, "USUBJID": uid, "AGE": r.get("AGE"),
            "SEX": "F",  # mBC trial, no sex var provided (disclosed assumption)
            "RACE": RACE_MAP.get(str(r.get("RACE_GEN", "")).strip(), "UNKNOWN"),
            "ARM": f"Treatment {arm}", "ARMCD": arm,
            # Single-arm trial, all subjects treated -> actual arm == planned arm.
            # Safe to map here (unlike Synta) because CA012 HAS an EX domain, so
            # ACTARMCD does not make A09/A14 false-fire on clean data (every
            # subject has both a disposition and an exposure record).
            "ACTARM": f"Treatment {arm}", "ACTARMCD": arm,
            "RFSTDTC": rfst, "RFXSTDTC": rfst, "RFXENDTC": rfen,
        })
    return pd.DataFrame(rows)


def build_ta(demo: pd.DataFrame, studyid: str) -> pd.DataFrame:
    arms = sorted({str(a or "").strip() or "B" for a in demo.get("ELIG_007", pd.Series(["B"]))})
    return pd.DataFrame([{
        "STUDYID": studyid, "ARMCD": a, "ARM": f"Treatment {a}",
        "TAETORD": 1, "ETCD": f"EL{i:02d}", "ELEMENT": "Treatment", "TASEQ": i,
    } for i, a in enumerate(arms, start=1)])


def build_ds(eosr: pd.DataFrame, studyid: str) -> pd.DataFrame:
    rows: list[dict] = []
    seq: dict[str, int] = {}
    for _, r in eosr.iterrows():
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        disc = str(r.get("EOSR_003", "") or "").strip()
        decod = "DISCONTINUED" if disc == "1" else "COMPLETED" if disc == "2" else "OTHER"
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid, "DSSEQ": seq[uid],
            "DSDECOD": decod, "DSCAT": "DISPOSITION EVENT",
            "DSTERM": str(r.get("EOSR_004", "") or ""),
            "DSSTDTC": _iso(r.get("EOSRDAY_001")), "EPOCH": "TREATMENT",
        })
    return pd.DataFrame(rows)


# Solicited-toxicity columns in `toxy` -> AETERM (verified against the data dictionary).
TOXY_TERMS = {
    "TOXY_001": "Nausea", "TOXY_002": "Vomiting", "TOXY_003": "Diarrhea",
    "TOXY_004": "Mucositis/stomatitis", "TOXY_005": "Alopecia", "TOXY_006": "Infection",
}
# CTC grade -> CDISC severity. Grade 'U' (unknown) and 0/blank are not emitted.
GRADE_SEV = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}


def build_ae(toxy: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """AE domain from the solicited-toxicity assessments (`toxy`).

    CA012 collects six solicited toxicities (nausea, vomiting, diarrhea,
    mucositis, alopecia, infection) graded per assessment, with a day-offset
    onset (``TOXYDAY_000``). Each graded (>0) toxicity becomes one AE record.

    Faithful-mapping caveat (disclosed): ``toxy`` records **no drug-causality /
    relationship variable**, so ``AEREL`` is *not* emitted. The cross-domain
    archetype A03 (exposure-start-after-*attributed*-AE) therefore cannot be
    exercised on this trial — its SHACL join requires an attributed AE
    (``AEREL`` in {Y, PROBABLE, POSSIBLE}). This is an honest data-availability
    boundary, not a detector gap (see ``run_e2_real_data.not_applicable``).
    """
    rows: list[dict] = []
    seq: dict[str, int] = {}
    for _, r in toxy.sort_values(["RSUBJ_ID", "TOXYDAY_000"]).iterrows():
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        dtc = _iso(r.get("TOXYDAY_000"))
        for col, term in TOXY_TERMS.items():
            grade = str(r.get(col, "") or "").strip()
            if grade not in GRADE_SEV:  # skip 0 / 'U' / blank
                continue
            seq[uid] = seq.get(uid, 0) + 1
            rows.append({
                "STUDYID": studyid, "USUBJID": uid, "AESEQ": seq[uid],
                "AETERM": term, "AEDECOD": term, "AETOXGR": grade,
                "AESEV": GRADE_SEV[grade], "AESTDTC": dtc, "EPOCH": "TREATMENT",
                # AEREL intentionally omitted: no causality variable in source.
            })
    return pd.DataFrame(rows)


def build_ex(dose: pd.DataFrame, studyid: str) -> pd.DataFrame:
    """EX domain from dose records (start/stop dates from day offsets)."""
    rows: list[dict] = []
    seq: dict[str, int] = {}
    for _, r in dose.sort_values(["RSUBJ_ID", "DOSEDAY_001"]).iterrows():
        uid = _usubjid(studyid, r["RSUBJ_ID"])
        st, en = _iso(r.get("DOSEDAY_001")), _iso(r.get("DOSEDAY_003"))
        if not st and not en:
            continue
        seq[uid] = seq.get(uid, 0) + 1
        rows.append({
            "STUDYID": studyid, "USUBJID": uid, "EXSEQ": seq[uid],
            "EXTRT": "Treatment B", "EXSTDTC": st, "EXENDTC": en,
            "EPOCH": "TREATMENT",
        })
    return pd.DataFrame(rows)


# -- write --------------------------------------------------------------------

def _write_xpt(df: pd.DataFrame, path: Path, domain: str) -> None:
    if df.empty:
        logger.warning("domain %s is empty — skipping write", domain)
        return
    df = df.copy()
    df.insert(0, "DOMAIN", domain)
    sort_cols = [c for c in ("USUBJID", "VISITNUM", f"{domain}SEQ") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    pyreadstat.write_xport(df, str(path), file_format_version=5, table_name=domain)
    logger.info("wrote %s rows=%d -> %s", domain, len(df), path)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Map CA012 (PDS 107) legacy -> SDTM.")
    p.add_argument(
        "--src", type=Path,
        default=Path("data/real_oncology_data/AllProvidedFiles_107/CA012 Data Files"),
    )
    p.add_argument("--out", type=Path, default=Path("data/real_sdtm/ca012"))
    p.add_argument("--studyid", default=STUDYID_DEFAULT)
    a = p.parse_args(argv)

    wl = _load(a.src, "wclesion")
    wr = _load(a.src, "wcresp")
    demo = _load(a.src, "demo")
    dose = _load(a.src, "dose")
    eosr = _load(a.src, "eosr")
    toxy = _load(a.src, "toxy")

    tu = build_tu(wl, a.studyid)
    tr = build_tr(wl, a.studyid)
    rs = build_rs(wr, a.studyid)
    ex = build_ex(dose, a.studyid)
    dm = build_dm(demo, ex, a.studyid)
    ds = build_ds(eosr, a.studyid)
    ta = build_ta(demo, a.studyid)
    ae = build_ae(toxy, a.studyid)

    _write_xpt(tu, a.out / "tu.xpt", "TU")
    _write_xpt(tr, a.out / "tr.xpt", "TR")
    _write_xpt(rs, a.out / "rs.xpt", "RS")
    _write_xpt(dm, a.out / "dm.xpt", "DM")
    _write_xpt(ds, a.out / "ds.xpt", "DS")
    _write_xpt(ta, a.out / "ta.xpt", "TA")
    _write_xpt(ex, a.out / "ex.xpt", "EX")
    _write_xpt(ae, a.out / "ae.xpt", "AE")

    print(
        f"CA012 -> SDTM: TU={len(tu)} TR={len(tr)} RS={len(rs)} DM={len(dm)} "
        f"DS={len(ds)} TA={len(ta)} EX={len(ex)} AE={len(ae)} "
        f"subjects={dm['USUBJID'].nunique()}"
    )


if __name__ == "__main__":
    main()
