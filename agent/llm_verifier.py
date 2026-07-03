"""Dual-channel LLM verifier for A19 (RECIST Table 7 contradiction).

Runs an independent LLM-based RECIST Table 7 reasoning check alongside
the deterministic `table7.lookup_table7` implementation.  Supports
multi-model cross-validation via OpenRouter (GPT-4o, Claude 3.5 Sonnet)
and the direct DeepSeek API.

Usage::

    results = run_multi_model_verification(graph)
    # [{model, subject, deterministic_expected, llm_expected, agree, raw}, ...]
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rdflib import Graph

from agent.orchestrator import (
    CAVE, CDISC, TARGET_TEST, NONTARGET_TEST, NEWLEC_TEST,
    _rs_records, _has_new_lesion, _find_test,
)
from agent.table7 import lookup_table7

logger = logging.getLogger(__name__)

# ── Model registry ────────────────────────────────────────────────────────

MODELS: dict[str, dict[str, str]] = {
    "deepseek-v3": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "gpt-4o": {
        "env_key": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o",
    },
    "claude-sonnet-4": {
        "env_key": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-sonnet-4",
    },
    "glm-4.6": {
        "env_key": "GLM_API_KEY",
        "base_url": "https://api.z.ai/api/paas/v4/",
        "model": "glm-4.6",
    },
}

# ── RECIST Table 7 prompt ─────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a clinical data validation expert specializing in RECIST 1.1 oncology response criteria.
Your task is to determine the expected overall response using RECIST 1.1 Table 7.

RECIST 1.1 Table 7 maps (target_response, nontarget_response, new_lesions) to overall_response:
- CR + CR + No → CR
- CR + Non-CR/Non-PD + No → PR
- PR + Any non-PD + No → PR
- SD + Any non-PD + No → SD
- PD + Any + Any → PD
- Any + PD + Any → PD
- Any + Any + Yes → PD
- NE + Any non-PD + No → NE

Respond ONLY with a JSON object: {"expected_overall": "<response>", "reasoning": "<brief>"}
"""


def _make_user_prompt(
    target: str, nontarget: str, new_lesions: str, actual: str,
) -> str:
    return (
        f"A subject has the following RECIST assessment data:\n"
        f"- Target lesion response: {target}\n"
        f"- Non-target lesion response: {nontarget}\n"
        f"- New lesions: {new_lesions}\n"
        f"- Recorded overall response (RSORRES): {actual}\n\n"
        f"Using RECIST 1.1 Table 7, determine the expected overall response. "
        f"Is the recorded response consistent with the expected response?"
    )


# ── LLM call wrapper ──────────────────────────────────────────────────────

def _call_llm(
    model_key: str,
    system: str,
    user: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Call an LLM via OpenAI-compatible API. Returns parsed JSON or error."""
    import openai

    spec = MODELS[model_key]
    api_key = os.environ.get(spec["env_key"], "")
    if not api_key:
        return {"error": f"Missing API key: {spec['env_key']}"}

    client = openai.OpenAI(
        api_key=api_key,
        base_url=spec["base_url"],
    )

    # GLM-4.6 defaults to thinking mode which may return empty content
    extra = {}
    if "glm" in model_key.lower():
        extra["extra_body"] = {"thinking": {"type": "disabled"}}

    try:
        resp = client.chat.completions.create(
            model=spec["model"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=300,
            **extra,
        )
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            return {"error": "Empty response from model"}
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)
        # Normalize verbose response codes: "Stable Disease (SD)" → "SD"
        if "expected_overall" in result:
            result["expected_overall"] = _normalize_response(
                result["expected_overall"]
            )
        return result
    except json.JSONDecodeError:
        return {"expected_overall": content, "reasoning": "raw_text", "parse_error": True}
    except Exception as exc:
        return {"error": str(exc)}


# Response normalization map for verbose LLM outputs
_RESPONSE_ALIASES: dict[str, str] = {
    "COMPLETE RESPONSE": "CR",
    "COMPLETE REMISSION": "CR",
    "PARTIAL RESPONSE": "PR",
    "PARTIAL REMISSION": "PR",
    "STABLE DISEASE": "SD",
    "PROGRESSIVE DISEASE": "PD",
    "NOT EVALUABLE": "NE",
    "NOT EVALUATED": "NE",
}


def _normalize_response(raw: str) -> str:
    """Normalize verbose LLM response codes to RECIST abbreviations."""
    s = raw.strip().upper()
    # Direct match (CR, PR, SD, PD, NE)
    if s in ("CR", "PR", "SD", "PD", "NE"):
        return s
    # Check aliases
    for alias, code in _RESPONSE_ALIASES.items():
        if alias in s:
            return code
    # Extract parenthetical abbreviation: "Stable Disease (SD)" → "SD"
    import re
    m = re.search(r"\(([A-Z]{2})\)", s)
    if m:
        return m.group(1)
    return s


# ── Verification logic ────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """Result of a single model's A19 verification for one subject."""
    model: str
    subject: str
    target_response: str
    nontarget_response: str
    new_lesion_status: str
    actual_overall: str
    deterministic_expected: str
    llm_expected: str = ""
    agree_with_deterministic: bool = False
    agree_with_actual: bool = False
    is_contradiction: bool = False
    llm_reasoning: str = ""
    error: str = ""


def _extract_subject_data(
    g: Graph, usubjid: str,
) -> dict[str, str | None]:
    """Extract RECIST assessment data for a subject from the RDF graph."""
    records = _rs_records(g, usubjid)
    target, _ = _find_test(records, TARGET_TEST)
    nontarget, _ = _find_test(records, NONTARGET_TEST)

    # New lesion status
    new_lesion = "NO"
    for _, tc, val in records:
        if tc.upper() == NEWLEC_TEST:
            new_lesion = "YES" if val.upper() == "Y" else "NO"
            break
    else:
        if _has_new_lesion(g, usubjid):
            new_lesion = "YES"

    return {
        "target": target,
        "nontarget": nontarget,
        "new_lesion": new_lesion,
        "actual": target,  # OVRLRESP is used as actual overall
    }


def verify_subject(
    g: Graph,
    usubjid: str,
    model_key: str = "deepseek-v3",
) -> VerificationResult:
    """Verify a single subject's overall response using both channels."""
    data = _extract_subject_data(g, usubjid)
    result = VerificationResult(
        model=model_key,
        subject=usubjid,
        target_response=data["target"] or "",
        nontarget_response=data["nontarget"] or "",
        new_lesion_status=data["new_lesion"],
        actual_overall=data["actual"] or "",
        deterministic_expected="",
    )

    # Channel A: Deterministic
    if data["target"] and data["nontarget"] and data["new_lesion"]:
        det = lookup_table7(data["target"], data["nontarget"], data["new_lesion"])
        result.deterministic_expected = det or "UNKNOWN"
    else:
        result.deterministic_expected = "INSUFFICIENT_DATA"

    # Channel B: LLM
    if not data["target"] or not data["nontarget"]:
        result.error = "Insufficient RS data for LLM verification"
        return result

    user_prompt = _make_user_prompt(
        data["target"], data["nontarget"], data["new_lesion"], data["actual"] or "UNKNOWN",
    )
    llm_resp = _call_llm(model_key, SYSTEM_PROMPT, user_prompt)

    if "error" in llm_resp:
        result.error = llm_resp["error"]
        return result

    llm_expected = llm_resp.get("expected_overall", "").upper().strip()
    result.llm_expected = llm_expected
    result.llm_reasoning = llm_resp.get("reasoning", "")
    result.agree_with_deterministic = (
        llm_expected == result.deterministic_expected.upper()
    )
    result.agree_with_actual = llm_expected == result.actual_overall.upper()
    result.is_contradiction = llm_expected != result.actual_overall.upper()

    return result


def run_multi_model_verification(
    g: Graph,
    models: list[str] | None = None,
    output_path: Path | None = None,
) -> list[dict]:
    """Run A19 verification across multiple models for all subjects in the graph.

    Returns a list of result dicts and optionally writes JSON to output_path.
    """
    from rdflib import URIRef
    from rdflib.namespace import RDF

    if models is None:
        models = list(MODELS.keys())

    # Find all subjects with RS records
    subjects: set[str] = set()
    for s in g.subjects(RDF.type, URIRef(f"{CAVE}RS")):
        for v in g.objects(s, URIRef(f"{CAVE}USUBJID")):
            subjects.add(str(v))

    results: list[dict] = []
    for model_key in models:
        logger.info("Running verification with model: %s", model_key)
        for subj in sorted(subjects):
            vr = verify_subject(g, subj, model_key)
            results.append(asdict(vr))
            status = "✓" if vr.agree_with_deterministic else "✗"
            logger.info(
                "  %s [%s] det=%s llm=%s %s",
                subj, model_key, vr.deterministic_expected,
                vr.llm_expected, status,
            )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8",
        )

    return results
