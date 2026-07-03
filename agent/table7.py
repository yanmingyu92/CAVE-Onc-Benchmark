"""RECIST 1.1 Table 7 — overall response lookup.

Maps the triple (target_response, nontarget_response, new_lesions)
to the expected overall response per RECIST 1.1 Table 7.

Response values are normalised to uppercase.  The sentinel
``"NON-CR/NON-PD"`` (with slash) is accepted alongside ``"NON-CR NON-PD"``.
"""

from __future__ import annotations

from typing import Literal

# -- Normalised response types -------------------------------------------------

TargetR = Literal["CR", "PR", "SD", "PD", "NE"]
NontargetR = Literal["CR", "NON-CR/NON-PD", "PD", "NE"]
NewLesion = Literal["NO", "YES"]
OverallR = Literal["CR", "PR", "SD", "PD", "NE"]

# -- Table 7 matrix ------------------------------------------------------------
# Key: (target, nontarget, new_lesions) → overall response
# Only clinically meaningful combinations per RECIST 1.1 are listed.
TABLE_7: dict[tuple[str, str, str], str] = {
    # --- Target CR ---
    ("CR", "CR", "NO"): "CR",
    ("CR", "NON-CR/NON-PD", "NO"): "PR",
    ("CR", "PD", "NO"): "PD",
    ("CR", "NE", "NO"): "PR",
    # --- Target PR ---
    ("PR", "CR", "NO"): "PR",
    ("PR", "NON-CR/NON-PD", "NO"): "PR",
    ("PR", "PD", "NO"): "PD",
    ("PR", "NE", "NO"): "PR",
    # --- Target SD ---
    ("SD", "CR", "NO"): "SD",
    ("SD", "NON-CR/NON-PD", "NO"): "SD",
    ("SD", "PD", "NO"): "PD",
    ("SD", "NE", "NO"): "SD",
    # --- Target PD ---
    ("PD", "CR", "YES"): "PD",
    ("PD", "NON-CR/NON-PD", "YES"): "PD",
    ("PD", "PD", "YES"): "PD",
    ("PD", "NE", "YES"): "PD",
    # Any new lesion → PD regardless of target / nontarget
    ("CR", "CR", "YES"): "PD",
    ("CR", "NON-CR/NON-PD", "YES"): "PD",
    ("CR", "PD", "YES"): "PD",
    ("CR", "NE", "YES"): "PD",
    ("PR", "CR", "YES"): "PD",
    ("PR", "NON-CR/NON-PD", "YES"): "PD",
    ("PR", "PD", "YES"): "PD",
    ("PR", "NE", "YES"): "PD",
    ("SD", "CR", "YES"): "PD",
    ("SD", "NON-CR/NON-PD", "YES"): "PD",
    ("SD", "NE", "YES"): "PD",
    # --- Target NE ---
    ("NE", "CR", "NO"): "NE",
    ("NE", "NON-CR/NON-PD", "NO"): "NE",
    ("NE", "PD", "NO"): "PD",
    ("NE", "NE", "NO"): "NE",
    ("NE", "CR", "YES"): "PD",
    ("NE", "NON-CR/NON-PD", "YES"): "PD",
    ("NE", "NE", "YES"): "PD",
}


def _norm(s: str) -> str:
    """Normalise a response string for lookup."""
    s = s.strip().upper()
    # Accept variants of Non-CR/Non-PD
    if s in ("NON-CR/NON-PD", "NON-CR NON-PD", "NON-CR/NON-PD", "NON-CR NON-PD"):
        return "NON-CR/NON-PD"
    # Normalise new-lesion flags
    if s in ("N", "NO", "FALSE"):
        return "NO"
    if s in ("Y", "YES", "TRUE"):
        return "YES"
    return s


def _norm_target(s: str) -> str:
    """Normalise a target response — NON-CR/NON-PD maps to SD in target context."""
    n = _norm(s)
    # Per RECIST 1.1, NON-CR/NON-PD is only a valid non-target response category.
    # If it appears as a target response, it is clinically equivalent to SD.
    if n == "NON-CR/NON-PD":
        return "SD"
    return n


def lookup_table7(
    target_response: str,
    nontarget_response: str,
    new_lesions: str,
) -> str | None:
    """Return expected overall response, or ``None`` if unknown combination."""
    key = (_norm_target(target_response), _norm(nontarget_response), _norm(new_lesions))
    return TABLE_7.get(key)
