# SPEC: guardbank guardrails (v2, approved 2026-11-19)

Domain: customer-support RAG assistant for a fictional Nepali bank, "Sagarmatha Digital Bank". No real bank names or branding.

## 1. Shared result type
Every detector returns `GuardResult(detected: bool, score: float, spans: list[Span], category: str|None, action: str, latency_ms: float)`. The pipeline, tests, eval and audit log all read this object.

Actions: `allow | redact | block | route | drop_chunk | regenerate | fallback`.

## 2. Pipeline order
1. Normalizer (NFKC, strip zero-width, homoglyphs, Devanagari digits to ASCII, decode obvious base64/hex and scan decoded text too).
2. Input PII: redact to typed tokens (`<PHONE_1>`), kept in a per-session vault.
3. Input injection: block if regex high-confidence OR classifier score >= tau.
4. Topic router (crisis keyword fast-path first, then classifier), before retrieval. It reads the unredacted text inside the process (only its verdict is logged), so redaction cannot hide crisis words.
5. Retriever (top-4); injection scan on every chunk; poisoned chunk dropped.
6. LLM (Claude Opus 4.6 on Amazon Bedrock, model in config/env; `MockLLM` for tests/CI) returns JSON; canary token in system prompt.
7. Output: schema, groundedness, sensitive-info checks, then `remediation.py` decides the final reply.
8. Audit log: each stage appends verdict, score, latency; entries are SHA-256 hash-chained JSONL.

## 3. Input guardrails
| Guardrail | Detection | Action | Known limits |
|---|---|---|---|
| PII | Presidio built-ins, custom Nepal recognizers (citizenship no., 9-digit PAN, +977 mobiles and landlines, account no. with context words), GLiNER-PII | Redact to typed token; card numbers/OTP/passwords redacted with "never share this" warning | Spelled-out digits (Devanagari digits are normalized to ASCII), Romanized names, PII split across turns, order-ID false positives |
| Prompt injection | Pruned regex bank + classifier (Prompt Guard 2 or DeBERTa) + canary + chunk scan | Direct attack: generic refusal + audit event. Poisoned chunk: drop silently, log | Semantic or multi-turn attacks, Romanized Nepali, over-flagging "ignore my last message" |
| Sensitive topic | Crisis keywords + embedding/logistic-regression classifier | Routing table below | Fuzzy category boundaries, small training set |

### Routing table (goes verbatim in README)
| Category | Example | Action |
|---|---|---|
| Self-harm / crisis | "I can't repay the loan, I want to end it" | Empathy + verified Nepal helpline + offer human agent. Never refuse coldly. Helpline numbers verified from an official source before use. |
| Scam / fraud victim | "Someone called and I gave my OTP" | Card-block steps from corpus + `escalate: true` |
| Committing fraud | "Open an account with a fake citizenship card" | Hard block + audit |
| Investment / legal advice | "Should I put my savings in NEPSE?" | General info from corpus + disclaimer, no personal recommendation |
| Complaint / dispute | "Your branch charged me twice" | Answer + grievance process, `escalate: true` |
| Off-topic | "Write me a poem" | Polite redirect to banking scope |
| Normal banking | "What is the ATM withdrawal limit?" | Allow |

## 4. Output guardrails
Response schema (Pydantic v2): `answer` (1..1200 chars), `citations: list[str]` (must exist in retrieved set), `intent` (account|cards|loans|fees|kyc|complaint|other), `confidence` (0..1), `escalate: bool`, `refusal_reason: str|None`. Citations non-empty unless `refusal_reason` is set. `escalate` must be true when intent is `complaint`.

| Guardrail | Detection | Limits |
|---|---|---|
| Schema | Pydantic parse, enum/range, citation-exists, escalate rule. Tested by fault injection | Valid structure says nothing about truth |
| Groundedness | Split answer into claims; NLI score vs cited chunks (HHEM-2.1-open); exact match of every number, percentage, amount, date | Paraphrase and multi-hop false flags, 512-token limit, checks the corpus not the world |
| Sensitive info | Re-run PII on output; PII not in this user's input = third-party leak; canary; embedding similarity to system prompt | Cannot catch invented-but-fake-looking PII, paraphrased leaks below threshold |

### Invalid-response policy (`remediation.py`)
| Failure | Action |
|---|---|
| Schema invalid | Regenerate with the error fed back, max 2 retries, then safe fallback |
| 1+ unsupported claims, score >= 0.5 | Regenerate once (temp 0, "answer only from context"); still failing: strip unsupported sentences and add "I couldn't verify the rest, please confirm with a branch" |
| Score < 0.5 or no citations | Safe fallback + `escalate: true` |
| Third-party PII in output | Redact spans, log incident |
| User's own PII echoed | Partial mask |
| Canary or system-prompt leak | Block the whole response, high-severity log |

## 5. Test case format (`tests/cases.yaml`)
```yaml
- id: INJ-03
  category: malicious_input
  input: "..."
  reference_docs: []
  expected: {stage: input.injection, action: block}
```
40+ cases: 8 normal, 8 malicious, 8 sensitive-info, 6 sensitive-topic, 5 invalid-output, 5 unsupported-claim. The eval script fills `actual` and `pass`.

## 6. Evaluation
Per-guardrail labeled sets, ~250 items (stretch ~400), split 30% dev / 70% test. Thresholds tuned on dev only, frozen, reported on test. Metrics: precision, recall, F1, FPR, FP and FN counts with every FN/FP listed by id, Wilson 95% CI. Ablations: injection (regex vs classifier vs hybrid), groundedness (keyword vs NLI vs NLI + number check). Threshold sweeps for tau and tau_g. Latency p50/p95 with and without GPU models.

## 7. Out of scope (unless time remains)
Streamlit UI, Llama Guard 4, Qwen3Guard, multi-turn PII tracking, real-bank data.

## 8. Environment
Python 3.11 target (laptop has 3.12; code must run on both). Thresholds and model names live in `config/guardrails.yaml`. ML models sit behind one interface with CPU stubs, so pytest runs without a GPU. Colab Pro runs the LLM and real models.

## 9. Claude Code development layer
Built and used during development; documented in `docs/claude-code-workflow.md` with a log of real use.

| Feature | Where | Purpose |
|---|---|---|
| CLAUDE.md | `CLAUDE.md` | Commands, layout, rules (spec first, failing test first, thresholds only in YAML, no secrets, never push to main) |
| Spec-driven | `SPEC.md` + `docs/specs/<feature>.md` per branch | Delta approved before code |
| Hooks | `.claude/settings.json`, `.claude/hooks/` | PostToolUse: ruff format/fix on `.py`. PreToolUse(Bash): block push to main, `--force`, date overrides, staging `.env`. Stop: fast unit tests |
| Skills | `.claude/skills/{add-test-case,run-eval,nepal-recognizer}` | Repeatable project tasks |
| Subagents | `.claude/agents/{red-teamer,guardrail-reviewer,eval-analyst}.md` | Adversarial inputs, read-only spec review, failure-analysis drafts |
| MCP | `src/guardbank/mcp_server.py`, `.mcp.json` | Tools `check_input`, `check_output`, `run_case` |
| Plugin | `plugins/guardbank-dev/`, `.claude-plugin/marketplace.json` | Bundles skills, agents, hooks |
| Context mgmt | `docs/claude-code-workflow.md`, permission `deny` rules | `/clear` per branch, `/compact` with focus, Explore subagents, keep eval data/model caches out of context |

## 10. Git workflow
- One feature per branch (`chore/`, `feat/`, `fix/`, `docs/`) in the order of `docs/roadmap.md`; conventional commits, real timestamps, no force-push.
- Royas is the sole author; no co-author trailers.
- `main` is protected: PR required, no force-push, no deletion; CI required once it exists.
- PR per branch with summary, spec link, test plan; CI (ruff + pytest, py3.11/3.12, mock LLM, stub models) must be green.
- Royas merges every PR; the next branch starts from updated `main`.

## Inputs needed during the build
- Bedrock credentials (`HOSTED_MODEL`, `BEDROCK_REGION`, `BEDROCK_API_KEYS`) in local `.env` (gitignored).
- Hugging Face token, with the Prompt Guard 2 licence accepted.
