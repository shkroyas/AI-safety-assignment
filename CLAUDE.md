# guardbank — project instructions

Guardrails for a customer-support RAG assistant of the fictional "Sagarmatha Digital Bank".
Trustworthy AI Assignment 1. **SPEC.md is the source of truth**; read the relevant section
before changing behaviour.

## Commands
- `uv sync` — install (Python 3.11+; code must run on 3.11 and 3.12)
- `uv run pytest -q -m "not slow and not live"` — fast tests (mock LLM, stub models)
- `uv run pytest -q` — all tests (slow = real ML models; live = Claude API)
- `uv run ruff check . && uv run ruff format --check .`
- `make eval` — regenerate every table and chart in `eval/results/`

## Layout
- `src/guardbank/input/` normalizer, pii, injection, topics
- `src/guardbank/output/` schema, groundedness, leakage
- `src/guardbank/rag/` retriever, llm (Claude + MockLLM), prompts
- `src/guardbank/{pipeline,remediation,audit,api,mcp_server}.py`
- `config/guardrails.yaml` — every threshold, model name, routing rule
- `data/corpus/` policy docs (+ poisoned docs), `data/eval/` labeled sets
- `tests/cases.yaml` end-to-end cases; `eval/run_eval.py` metrics

## Rules
- Spec first: a behaviour change starts as an edit to SPEC.md or `docs/specs/<feature>.md`, approved by Royas.
- Then a failing test, then the smallest code that passes it. On failure, find the cause; no trial-and-error fixes.
- Every detector returns `GuardResult` (SPEC §1). Thresholds and model names live only in YAML, never in code.
- ML models sit behind the `Detector` interface with a CPU stub; mark tests needing real models `@pytest.mark.slow`, Claude API tests `@pytest.mark.live`.
- Corpus and test data are synthetic. No real bank names, branding or real people's PII.
- Never read or commit `.env`. Keys come from Royas, never from searching the machine.

## Git
- One branch per feature (`feat/`, `fix/`, `chore/`, `docs/`); conventional commits; real timestamps.
- Never push to `main`, never force-push, never rewrite pushed history (enforced by `.claude/hooks/guard_bash.py`).
- `gh` calls use `GH_TOKEN=$(gh auth token -u shkroyas)`; check `gh api user -q .login` is `shkroyas` before a push or PR.
- Open the PR with a summary, spec link and test plan, wait for green CI, then stop. Royas merges.

## Context
- `/clear` between feature branches; the branch's spec delta + this file are enough to restart.
- Use an Explore subagent for wide searches; don't read `data/eval/` or model caches into context.
- How each Claude Code feature is used here: `docs/claude-code-workflow.md`.
