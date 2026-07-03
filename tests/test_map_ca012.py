"""Tests for the CA012 (PDS 107) legacy->SDTM mapper.

Raw PDS data is gitignored (sponsor terms), so these tests SKIP when the source
directory is absent (e.g. CI). When present they assert the structural and
fidelity invariants the CAVE engine relies on (Item E Phase 4).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts import map_ca012_to_sdtm as m

SRC = Path("data/real_oncology_data/AllProvidedFiles_107/CA012 Data Files")
RECIST_CODES = {"CR", "PR", "SD", "PD", "NE", "ND", ""}

pytestmark = pytest.mark.skipif(
    not (SRC / "wcresp.sas7bdat").exists(),
    reason="PDS CA012 raw data not present (gitignored)",
)


@pytest.fixture(scope="module")
def frames():
    sid = m.STUDYID_DEFAULT
    wl, wr = m._load(SRC, "wclesion"), m._load(SRC, "wcresp")
    demo, dose, eosr = m._load(SRC, "demo"), m._load(SRC, "dose"), m._load(SRC, "eosr")
    toxy = m._load(SRC, "toxy")
    ex = m.build_ex(dose, sid)
    return {
        "TU": m.build_tu(wl, sid), "TR": m.build_tr(wl, sid), "RS": m.build_rs(wr, sid),
        "DM": m.build_dm(demo, ex, sid), "DS": m.build_ds(eosr, sid),
        "TA": m.build_ta(demo, sid), "EX": ex, "AE": m.build_ae(toxy, sid),
    }


def test_all_domains_nonempty(frames):
    for dom in ("TU", "TR", "RS", "DM", "DS", "TA", "EX", "AE"):
        assert not frames[dom].empty, f"{dom} is empty"


def test_subject_conservation(frames):
    # every RS/TR/TU/EX/AE subject exists in DM
    dm_subj = set(frames["DM"]["USUBJID"])
    for dom in ("TR", "RS", "TU", "EX", "AE"):
        leaked = set(frames[dom]["USUBJID"]) - dm_subj
        assert not leaked, f"{dom} has subjects not in DM: {sorted(leaked)[:3]}"


def test_ae_faithful_and_unattributed(frames):
    """AE maps solicited toxicities faithfully but carries NO causality attribution.

    The absence of ``AEREL`` is the fidelity-honest reason archetype A03
    (exposure-after-attributed-AE) is not exercisable on CA012 — its SHACL join
    requires an attributed AE. Locking it here prevents a future mapper from
    silently fabricating attribution to "make A03 fire".
    """
    ae = frames["AE"]
    assert "AEREL" not in ae.columns, "toxy has no causality variable; AEREL must not be fabricated"
    assert set(ae["AETERM"].unique()) <= set(m.TOXY_TERMS.values())
    assert set(ae["AETOXGR"].unique()) <= set(m.GRADE_SEV), "only graded (>0) toxicities emitted"
    assert (ae["AESTDTC"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")).mean() > 0.9


def test_no_orphan_lesion_links(frames):
    tu_keys = set(zip(frames["TU"]["USUBJID"], frames["TU"]["TULNKID"]))
    tr = frames["TR"]
    orphans = [(u, l) for u, l in zip(tr["USUBJID"], tr["TRLNKID"]) if (u, l) not in tu_keys]
    assert not orphans, f"{len(orphans)} TR rows reference a missing TU lesion"


def test_recist_codelist(frames):
    rs = frames["RS"]
    resp = rs[rs["RSTESTCD"].isin(["OVRESP", "NTRGRESP", "OVRLRESP"])]["RSORRES"]
    bad = set(resp.unique()) - RECIST_CODES
    assert not bad, f"non-codelist RS responses: {bad}"


def test_sld_math_holds(frames):
    """SUMDIAM == sum of target LDIAM per (subject, visit) — fidelity lock.

    CA012's derived SLD matches exactly (verified 100%); we lock a high bar.
    """
    tr, rs = frames["TR"], frames["RS"]
    ld = tr[tr["TRTESTCD"] == "LDIAM"].groupby(["USUBJID", "VISITNUM"])["TRSTRESN"].sum()
    sd = rs[rs["RSTESTCD"] == "SUMDIAM"].set_index(["USUBJID", "VISITNUM"])["RSSTRESN"]
    both = pd.concat([ld.rename("ld"), sd.rename("sd")], axis=1).dropna()
    assert len(both) > 100
    match = (both["ld"].round(1) == both["sd"].round(1)).mean()
    assert match >= 0.95, f"SLD-math match only {match:.2%}"


def test_overall_response_is_ovrlresp(frames):
    """Overall response must be RSTESTCD=OVRLRESP (hardened archetype shapes)."""
    rs = frames["RS"]
    overall = rs[rs["RSCAT"] == "OVERALL RESPONSE"]
    assert not overall.empty
    assert set(overall["RSTESTCD"].unique()) == {"OVRLRESP"}


def test_ex_dates_present_and_iso(frames):
    ex = frames["EX"]
    starts = ex["EXSTDTC"].astype(str)
    assert (starts.str.match(r"\d{4}-\d{2}-\d{2}")).mean() > 0.5
    # DM reference dates derived from EX
    dm = frames["DM"]
    assert (dm["RFXSTDTC"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")).any()


def test_dm_single_arm(frames):
    dm = frames["DM"]
    assert set(dm["ARMCD"].unique()) == {"B"}
    assert set(dm["SEX"].unique()) == {"F"}  # disclosed mBC assumption
