# agent/ — LangGraph L3 Orchestrator

LangGraph agent with DeepSeek V4 / Zhipu GLM dual-vendor router.

## Scope (T5.5)
- L3 trigger heuristic: sh:Warning severity + overlapping L1 flags
- A19 (Table 7 overall response) routing — sole L2 archetype under 2-layer architecture
- Tool-constrained, deterministic state machine
- Dual-vendor cross-check: DeepSeek vs GLM divergence >5% triggers manual review

## Architecture (2-layer — per T3.3 decision)
The DAG/causal layer (pgmpy, DoWhy) was dropped from v1. The agent layer
handles compositional reasoning that individual SHACL shapes cannot express.
