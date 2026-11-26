# Spec delta: feat/remediation-pipeline

SPEC section: 2. Pipeline order (all 8 steps) + 4. Output guardrails (invalid-response policy). ≤40 lines.

## Scope
- `pipeline.py`: `Pipeline.from_settings(settings, llm, audit=None)`, `run(text, session) -> PipelineResult`
  (`request_id`, `text` = final user-facing reply, `reply`, `escalate`, `outcome`, `stages: list[GuardResult]`, `llm_calls`).
  `Session` holds the per-session `PiiVault`. `Assistant` stays as the unguarded baseline for the ablation.
- `remediation.py`: `Remediation` (texts + limits from YAML) decides after each output stage and emits a
  `GuardResult` (stage `"remediation"`, `details.reason`, `details.attempts`).

## Flow (stop at the first terminal step; every stage result is audited)
1. Normalizer → 2. PII redact (LLM, retrieval and topics only ever see redacted text) → 3. Injection on normalized + decoded:
   BLOCK → generic refusal, outcome `blocked`, no LLM call → 4. Topics: CRISIS / FRAUD_INTENT / OFF_TOPIC return the route's
   fixed `response` with no LLM call (outcomes `crisis`, `blocked`, `redirect`); answer routes carry `escalate`/`disclaimer` on.
5. Retrieve top_k → chunk scan drops poisoned chunks → system prompt with canary.
6. LLM → schema guard. Invalid: regenerate with the guard's `feedback` as a new user turn, at most `max_schema_retries` (2), then fallback.
7. Leakage canary/prompt check on every schema-valid answer: BLOCK → block message, outcome `blocked`, severity high.
8. Groundedness: REGENERATE → one retry at temperature 0 with `regenerate_instruction`; still REGENERATE → strip the unsupported
   sentences and append `strip_note`; FALLBACK at any point → fallback. Fallback = `fallback_text`, `escalate: true`, outcome `fallback`.
9. Leakage PII pass on the final answer text → redacted/masked text. Then append topic disclaimer and the input PII warning.
- `escalate` = reply.escalate OR topic escalate OR fallback. Outcome `answered` otherwise.
- Audit: one entry per stage, then a final `remediation` entry. Details are sanitised first: user/model text keys
  (`normalized`, `decoded`, `redacted`, `decoded_redacted`, `text`, `reply`) dropped, claims kept as scores only.
  The pipeline entry stores `input_len` + `input_sha256`, never raw input.

## Config (`config/guardrails.yaml`, new top-level `remediation:`)
- `max_schema_retries: 2`, `regenerate_instruction`, `strip_note` ("I couldn't verify the rest, please confirm with a branch."),
  `fallback_text` (apology + team follow-up + visit a branch), `block_text` (same generic refusal as injection).

## Tests first (`tests/test_pipeline.py`, all fast, MockLLM or scripted fakes)
- Input: `normal_answered`, `injection_blocked_no_llm`, `crisis_routed_no_llm`, `fraud_blocked`, `off_topic_redirect`,
  `advice_disclaimer`, `complaint_escalates`, `pii_redacted_before_llm`, `never_share_warning`, `poisoned_chunk_not_in_prompt`.
- Output: `schema_retry_then_ok`, `schema_fails_fallback` (3 calls), `unsupported_regenerated_temp0`, `unsupported_stripped`,
  `low_support_fallback`, `canary_leak_blocked`, `third_party_pii_redacted`, `audit_chain_intact_and_no_raw_input`.

## Out of scope
- API/MCP (`feat/api-mcp`); multi-turn history beyond the vault; real ML detectors (`feat/ml-detectors`).
