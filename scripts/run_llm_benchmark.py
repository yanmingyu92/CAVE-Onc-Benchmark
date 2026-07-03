"""P16 LLM integration benchmark — runs all 3 tiers.

Tier 1: Multi-model A19 verification (dual-channel)
Tier 2: Clinical trace explanations for all 20 detections
Tier 3: Uncertainty triage for protocol-dependent archetypes (A04, A07, A12, A20)

Outputs:
  eval/llm_verification_results.json   — Tier 1
  eval/llm_explanations.json           — Tier 2
  eval/llm_uncertainty_triage.json     — Tier 3
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = _ROOT / "eval"

# ── Load environment ──────────────────────────────────────────────────────

def _load_env():
    """Load .env into os.environ for API keys."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        logger.warning(".env not found at %s", env_path)
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if val and key not in os.environ:
            os.environ[key] = val

_load_env()


# ── Tier 1: Multi-model A19 verification ──────────────────────────────────

def run_tier1_verification():
    """Run dual-channel A19 verification across 3 models × all subjects."""
    from bench.injector import Injector
    from scripts.track_b_analysis import _frames_to_graph, _enrich_rs, ARCHETYPES
    from bench.mutations import MUTATIONS
    from agent.llm_verifier import run_multi_model_verification, MODELS

    logger.info("=" * 60)
    logger.info("TIER 1: Multi-model A19 verification")
    logger.info("=" * 60)

    # Load clean data and inject A19 specifically
    injector = Injector(output_dir="bench/output_track_b")
    clean_frames = injector._load_all()

    # Inject A19 mutation
    frames = {k: v.copy() for k, v in clean_frames.items()}
    frames, meta = MUTATIONS["A19"](frames)
    frames = _enrich_rs(frames)
    graph = _frames_to_graph(frames)

    # Determine which models have keys available
    available = []
    for model_key, spec in MODELS.items():
        env_key = spec["env_key"]
        if os.environ.get(env_key):
            available.append(model_key)
            logger.info("  Model %s: key available (%s)", model_key, env_key)
        else:
            logger.warning("  Model %s: key MISSING (%s) — skipping", model_key, env_key)

    if not available:
        logger.error("No LLM API keys available. Set DEEPSEEK_API_KEY or openrouter in .env")
        return {"error": "no_keys", "models_checked": list(MODELS.keys())}

    results = run_multi_model_verification(
        graph, models=available,
        output_path=EVAL_DIR / "llm_verification_results.json",
    )

    # Summary
    for model in available:
        model_results = [r for r in results if r["model"] == model]
        agree = sum(1 for r in model_results if r["agree_with_deterministic"])
        total = len(model_results)
        logger.info(
            "  %s: %d/%d agree with deterministic (%.1f%%)",
            model, agree, total, 100 * agree / total if total else 0,
        )

    return results


# ── Tier 2: Clinical trace explanations ───────────────────────────────────

def run_tier2_explanations():
    """Generate LLM explanations for all 20 archetype detections."""
    from agent.trace_explainer import TraceExplainer, ARCHETYPE_CONTEXT

    logger.info("=" * 60)
    logger.info("TIER 2: Clinical trace explanations")
    logger.info("=" * 60)

    # Build synthetic trace entries for all 20 archetypes
    trace_entries = []
    for aid in sorted(ARCHETYPE_CONTEXT.keys()):
        trace_entries.append({
            "archetype": aid,
            "subject": f"SUBJ-{aid}",
            "visit": "V2",
            "layer": "L1" if aid != "A19" else "L3",
            "severity": "violation",
            "shacl_shape": f"cave:Shape_Archetype_{aid}",
            "evidence_path": [
                {"type": "resultMessage", "value": ARCHETYPE_CONTEXT[aid]},
            ],
            "agent_trace": None,
        })

    # Find available model (prefer deepseek for cost)
    model = None
    if os.environ.get("DEEPSEEK_API_KEY"):
        model = "deepseek-v3"
    elif os.environ.get("openrouter"):
        model = "gpt-4o"

    if not model:
        logger.error("No LLM API keys available for explanations")
        return {"error": "no_keys"}

    logger.info("Using model: %s for %d explanations", model, len(trace_entries))
    explainer = TraceExplainer(model=model)

    results = []
    for entry in trace_entries:
        result = explainer.explain(entry)
        results.append(asdict(result))
        if result.error:
            logger.warning("  %s: ERROR — %s", result.archetype, result.error)
        else:
            logger.info("  %s: %s", result.archetype, result.summary[:80] if result.summary else "no summary")

    output_path = EVAL_DIR / "llm_explanations.json"
    output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    logger.info("Explanations saved to %s", output_path)

    return results


# ── Tier 3: Uncertainty triage ────────────────────────────────────────────

UNCERTAIN_ARCHETYPES = ["A04", "A07", "A12", "A20"]

TRIAGE_SYSTEM_PROMPT = """\
You are a senior clinical data reviewer for CDISC oncology submissions.

You are given a validation finding that has been flagged as potentially protocol-dependent.
Classify whether this is:
1. "genuine_violation" - a clear data quality issue regardless of protocol
2. "protocol_dependent" - may or may not be a violation depending on the study protocol
3. "false_alarm" - likely not a real issue

Respond with JSON:
{
  "verdict": "genuine_violation|protocol_dependent|false_alarm",
  "confidence": 0.0-1.0,
  "rationale": "Brief explanation of your classification"
}
"""

ARCHETYPE_TRIAGE_CONTEXT = {
    "A04": "Visit number mismatch between TR/RS and EX domains. Some protocols allow flexible visit windows where the same clinical assessment visit maps to different sequence numbers across domains. This could be a scheduling artifact rather than a data error.",
    "A07": "Partial Response (PR) claimed without a required confirmation visit. RECIST 1.1 requires confirmation for PR, but some protocols define modified criteria that waive this requirement. Additionally, if the subject discontinued before the confirmation window, this may not indicate data error.",
    "A12": "Disposition indicates death but no corresponding death date in DM or adverse event in AE. Some protocols record death through different mechanisms (e.g., separate death CRF) or the death may have occurred outside the study observation window.",
    "A20": "iRECIST confirmation requirement violated. iRECIST criteria are not universally adopted, and many oncology studies use standard RECIST 1.1. If the study protocol specifies RECIST 1.1 only, this check is not applicable.",
}


def run_tier3_triage():
    """Run uncertainty triage for protocol-dependent archetypes."""
    import openai

    logger.info("=" * 60)
    logger.info("TIER 3: Uncertainty triage for %s", UNCERTAIN_ARCHETYPES)
    logger.info("=" * 60)

    # Find all available models
    from agent.llm_verifier import MODELS
    available = []
    for model_key, spec in MODELS.items():
        if os.environ.get(spec["env_key"]):
            available.append(model_key)

    if not available:
        logger.error("No LLM API keys available for triage")
        return {"error": "no_keys"}

    results = []
    for aid in UNCERTAIN_ARCHETYPES:
        context = ARCHETYPE_TRIAGE_CONTEXT[aid]
        user_prompt = (
            f"ARCHETYPE: {aid}\n"
            f"CONTEXT: {context}\n\n"
            f"Based on your experience with CDISC oncology submissions, "
            f"classify this finding."
        )

        model_verdicts = []
        for model_key in available:
            spec = MODELS[model_key]
            api_key = os.environ.get(spec["env_key"], "")

            try:
                client = openai.OpenAI(api_key=api_key, base_url=spec["base_url"])
                # GLM-4.6 needs thinking disabled for JSON output
                extra = {}
                if "glm" in model_key.lower():
                    extra["extra_body"] = {"thinking": {"type": "disabled"}}
                resp = client.chat.completions.create(
                    model=spec["model"],
                    messages=[
                        {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=300,
                    **extra,
                )
                content = (resp.choices[0].message.content or "").strip()
                if not content:
                    raise ValueError("Empty response from model")
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                parsed = json.loads(content)
                model_verdicts.append({
                    "model": model_key,
                    "verdict": parsed.get("verdict", "unknown"),
                    "confidence": parsed.get("confidence", 0.0),
                    "rationale": parsed.get("rationale", ""),
                })
                logger.info(
                    "  %s [%s]: %s (conf=%.2f)",
                    aid, model_key,
                    parsed.get("verdict"), parsed.get("confidence", 0),
                )
            except Exception as exc:
                model_verdicts.append({
                    "model": model_key,
                    "verdict": "error",
                    "confidence": 0.0,
                    "rationale": str(exc),
                })
                logger.warning("  %s [%s]: ERROR — %s", aid, model_key, exc)

        # Compute consensus
        verdicts = [v["verdict"] for v in model_verdicts if v["verdict"] != "error"]
        consensus = max(set(verdicts), key=verdicts.count) if verdicts else "no_consensus"
        agreement = verdicts.count(consensus) / len(verdicts) if verdicts else 0.0

        results.append({
            "archetype": aid,
            "model_verdicts": model_verdicts,
            "consensus": consensus,
            "agreement_rate": round(agreement, 3),
        })

    output_path = EVAL_DIR / "llm_uncertainty_triage.json"
    output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    logger.info("Triage results saved to %s", output_path)

    return results


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    """Run all 3 tiers of P16 LLM integration benchmark."""
    logger.info("P16 LLM Integration Benchmark")
    logger.info("=" * 60)

    tier1 = run_tier1_verification()
    tier2 = run_tier2_explanations()
    tier3 = run_tier3_triage()

    # Summary report
    summary = {
        "tier1_verification": {
            "subjects_tested": len(tier1) if isinstance(tier1, list) else 0,
            "error": tier1.get("error") if isinstance(tier1, dict) else None,
        },
        "tier2_explanations": {
            "archetypes_explained": len(tier2) if isinstance(tier2, list) else 0,
            "error": tier2.get("error") if isinstance(tier2, dict) else None,
        },
        "tier3_triage": {
            "archetypes_triaged": len(tier3) if isinstance(tier3, list) else 0,
            "error": tier3.get("error") if isinstance(tier3, dict) else None,
        },
    }

    summary_path = EVAL_DIR / "llm_integration_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("\nSummary: %s", json.dumps(summary, indent=2))

    return summary


if __name__ == "__main__":
    main()
