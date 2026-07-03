"""LLM-powered clinical trace explainer for SHACL validation findings.

Transforms raw SHACL violation reports (technical RDF triples, shape IRIs,
constraint messages) into clinician-readable narratives with:
  - Subject/visit context
  - What was expected vs. found
  - RECIST/CDISC rule reference
  - Recommended action

Usage::

    explainer = TraceExplainer(model="deepseek-v3")
    narrative = explainer.explain(trace_entry, rdf_graph)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from rdflib import Graph, URIRef

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a senior CDISC clinical data reviewer specializing in SDTM oncology submissions.

Given a machine-generated validation finding from a SHACL graph constraint engine,
produce a clear, clinician-readable explanation. Your output must be a JSON object with:

{
  "summary": "One-sentence plain-English summary of the finding",
  "clinical_context": "What this means clinically (2-3 sentences)",
  "expected_vs_found": "What the data should show vs. what was found",
  "cdisc_reference": "Relevant CDISC IG section or RECIST 1.1 rule",
  "recommended_action": "What the data manager should do",
  "severity_assessment": "critical|major|minor"
}

Be precise, use CDISC terminology, and avoid jargon not familiar to statistical programmers.
Do NOT hallucinate CDISC rule IDs — if unsure, say "refer to SDTMIG 3.4 [domain] section."
"""

# Archetype clinical descriptions for context
ARCHETYPE_CONTEXT: dict[str, str] = {
    "A01": "SLD decrease ≥30% from baseline but overall response = PD (RECIST Table 7 contradiction)",
    "A02": "New lesion identified in TU but overall response not escalated to PD",
    "A03": "Exposure start date (EXSTDTC) after adverse event start date (AESTDTC) — temporal impossibility",
    "A04": "Visit number mismatch between TR/RS and EX domains for the same subject",
    "A05": "SUPPDM supplemental qualifier contradicts parent DM record (e.g., SEX mismatch)",
    "A06": "Non-target lesion PD without corresponding overall response escalation",
    "A07": "Partial Response claimed without required confirmation visit per RECIST 1.1",
    "A08": "Invalid RSORRES value not in RECIST controlled terminology",
    "A09": "Missing AE record for a subject with documented adverse event-related disposition",
    "A10": "Reference start date (RFSTDTC) derivation mismatch with earliest EX date",
    "A11": "Reference end date (RFENDTC) derivation mismatch with latest EX date",
    "A12": "Disposition records death but no corresponding death date or adverse event",
    "A13": "SUPPDM RACEOTH qualifier present but DM.RACE is not OTHER",
    "A14": "Subject assigned to treatment arm (DM.ARMCD) but has no exposure records (EX)",
    "A15": "Study day (DY) derivation inconsistent with reference start date",
    "A16": "Duplicate USUBJID within the same study",
    "A17": "ARMCD/ARM mismatch — subject assigned to arm code but ARM text differs from TA definition",
    "A18": "Tumor status indicates lesion present but no corresponding TR measurement",
    "A19": "RECIST Table 7 overall response contradiction (requires multi-domain reasoning)",
    "A20": "iRECIST confirmation requirement violated — response claimed without confirmation window",
}


def _build_context_prompt(
    trace_entry: dict,
    rdf_context: str = "",
) -> str:
    """Build the user prompt from a TraceEntry dict and optional RDF context."""
    archetype = trace_entry.get("archetype", "unknown")
    clinical_desc = ARCHETYPE_CONTEXT.get(archetype, "Unknown archetype")

    evidence = trace_entry.get("evidence_path", [])
    evidence_text = "\n".join(
        f"  - {e.get('type', 'unknown')}: {e.get('value', '')}"
        for e in evidence
    ) if evidence else "  (no evidence path recorded)"

    agent_trace = trace_entry.get("agent_trace")
    agent_text = ""
    if agent_trace:
        agent_text = f"\nAgent reasoning trace:\n  {json.dumps(agent_trace, indent=2)}"

    return (
        f"VALIDATION FINDING:\n"
        f"  Archetype: {archetype}\n"
        f"  Clinical meaning: {clinical_desc}\n"
        f"  Subject: {trace_entry.get('subject', 'unknown')}\n"
        f"  Visit: {trace_entry.get('visit', 'N/A')}\n"
        f"  Layer: {trace_entry.get('layer', 'L1')}\n"
        f"  Severity: {trace_entry.get('severity', 'violation')}\n"
        f"  SHACL shape: {trace_entry.get('shacl_shape', 'N/A')}\n"
        f"\nEvidence:\n{evidence_text}"
        f"{agent_text}"
        f"\n\nGenerate a clinician-readable explanation of this finding."
    )


@dataclass
class ExplanationResult:
    """Result of LLM trace explanation."""
    archetype: str
    subject: str
    model: str
    summary: str = ""
    clinical_context: str = ""
    expected_vs_found: str = ""
    cdisc_reference: str = ""
    recommended_action: str = ""
    severity_assessment: str = ""
    error: str = ""


class TraceExplainer:
    """Generates clinical explanations for SHACL validation findings via LLM."""

    # Model registry (same as llm_verifier)
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

    def __init__(self, model: str = "deepseek-v3") -> None:
        self.model = model
        if model not in self.MODELS:
            raise ValueError(f"Unknown model: {model}. Choose from {list(self.MODELS)}")

    def explain(
        self,
        trace_entry: dict,
        rdf_graph: Graph | None = None,
    ) -> ExplanationResult:
        """Generate a clinical explanation for a single trace entry."""
        import openai

        archetype = trace_entry.get("archetype", "unknown")
        subject = trace_entry.get("subject", "unknown")

        result = ExplanationResult(
            archetype=archetype,
            subject=subject,
            model=self.model,
        )

        spec = self.MODELS[self.model]
        api_key = os.environ.get(spec["env_key"], "")
        if not api_key:
            result.error = f"Missing API key: {spec['env_key']}"
            return result

        user_prompt = _build_context_prompt(trace_entry)

        try:
            client = openai.OpenAI(
                api_key=api_key,
                base_url=spec["base_url"],
            )
            resp = client.chat.completions.create(
                model=spec["model"],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            content = resp.choices[0].message.content.strip()

            # Parse JSON response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            parsed = json.loads(content)
            result.summary = parsed.get("summary", "")
            result.clinical_context = parsed.get("clinical_context", "")
            result.expected_vs_found = parsed.get("expected_vs_found", "")
            result.cdisc_reference = parsed.get("cdisc_reference", "")
            result.recommended_action = parsed.get("recommended_action", "")
            result.severity_assessment = parsed.get("severity_assessment", "")

        except json.JSONDecodeError:
            result.summary = content
            result.error = "JSON parse failed — raw text returned"
        except Exception as exc:
            result.error = str(exc)

        return result


def explain_all_detections(
    trace_entries: list[dict],
    model: str = "deepseek-v3",
    rdf_graph: Graph | None = None,
) -> list[dict]:
    """Generate explanations for a list of trace entries."""
    from dataclasses import asdict
    explainer = TraceExplainer(model=model)
    results = []
    for entry in trace_entries:
        result = explainer.explain(entry, rdf_graph)
        results.append(asdict(result))
        if result.error:
            logger.warning("  %s: ERROR — %s", result.archetype, result.error)
        else:
            logger.info("  %s: %s", result.archetype, result.summary[:80])
    return results
