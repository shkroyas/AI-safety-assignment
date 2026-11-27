# Spec delta: fix/output-pipeline

SPEC section: 4. Output guardrails (invalid-response policy) + 2. Pipeline order. From EVALUATION_RECOMMENDATIONS.md
P0-2 and P0-3, reproduced. ≤40 lines.

## Problems (reproduced)
1. Token overlap: an LLM echo "your password is <PASSWORD_1>" is matched twice: as the user's own vault token
   and by the PASSWORD rule. The two edits overlap and the text comes out "[hidden]SSWORD]", logged as a
   third-party PII incident.
2. Duplicate leakage check: on a normal one-shot answer, `output_leakage` runs on the same text before and
   after groundedness (two identical stages in every report; GLiNER and the embedder run twice).
3. Wrong verdict: when the final leakage check redacts PII, `remediation` still reports `allow / answered`,
   so the guardrail report and audit log hide a redaction.
4. `PipelineResult.reply.answer` keeps the unsanitized answer (raw third-party PII or stripped claims) for
   Python callers; the API's `reply` text is already sanitized.
5. Latent: the final leakage result is never checked for BLOCK. Today it cannot block (the stripped text is
   a subset of checked sentences), but nothing enforces that.

## Fix
1. `LeakageChecker`: a PII hit that overlaps a vault token span is skipped (the token edit wins).
2. `Pipeline`: the leakage result of the accepted answer is kept; leakage runs again only when the answer
   changed (regenerated or stripped). Normal stage order becomes: …, output_schema, output_leakage,
   output_groundedness, remediation (one leakage stage). `test_normal_answered` is updated to this order.
3. When the final leakage check redacts and nothing else changed the answer, remediation reports
   `redact` with reason `redacted_third_party_pii` or `redacted_own_pii` (outcome stays `answered`).
4. `PipelineResult.reply` is a copy with `answer` set to the sanitized text (before disclaimers/warnings).
5. A BLOCK from the final leakage check ends with `blocked` and the block text (guard; tested with a fake).

## Tests first
- `tests/output/test_leakage.py`: `<PASSWORD_1>`, `<OTP_1>`, `<EMAIL_1>` echoed after their context words give
  one OWN_PII edit each, clean text, no THIRD_PARTY_PII.
- `tests/test_pipeline.py`: one `output_leakage` stage on a normal answer; two when regenerated; third-party
  PII → remediation `redact` / `redacted_third_party_pii` and `reply.answer` without the number; fake final
  BLOCK → `blocked`.
- e2e cases unchanged in outcome; `make eval`, `make eval-full`, `make ablations` (latency should drop).

## Limits
- Stage counts in older artifacts (docs/demo/live_run.json, the demo video) show the old double stage until
  they are regenerated.
