# Spec delta: fix/output-overredaction

SPEC section: 4. Output guardrails (Sensitive info row). Found in docs/report (failure 5, live run). ≤40 lines.

## Problem
- Live reply (docs/demo/live_run.json) came back as "password [redacted PASSWORD]" ×3 and "[redacted LOCATION]"
  ×2 where the corpus says "1660-01-12345". No data leaked, but the scam-victim hotline was lost.
- PASSWORD, reproduced: output leakage re-runs the input PASSWORD rule, which takes the word after "password"
  with an optional marker. On a bank reply it captured ",", "reset", "attempts", "and"; those absent from the
  retrieved context ("reset", "attempts") were redacted as third-party PII.
- Hotline, not reproduced: rebuilt with the corpus spelling, the span is in the context and kept. The live span
  must have differed (boundaries or formatting); the raw reply was not stored, and `logs/` is not read.
- The leakage eval set has no password items and no formatted public numbers, so the eval could not see this.

## Fix (output side only; input PII unchanged)
- `output.leakage.password_requires_marker: true`: in model output a PASSWORD span needs an explicit marker
  ("password is X", "password: X", "password = X"); bare "password reset" is not a secret.
- `output.leakage.public_digits_min: 6`: a span with at least that many digits is public (kept) when its digit
  string appears in a number in the context, whatever the label or formatting ("**1660-01-12345**",
  "1660 01 12345"). Exact text match stays first.
- The user's own PII (vault) and canary / prompt-similarity checks are unchanged.

## New eval set (`data/eval/leakage_pii.jsonl`, reported as `leakage_pii`; same 30/70 split)
- ~16 label 0: grounded replies with password words ("password reset", "wrong password attempts") and corpus
  numbers in other formats, each with its context.
- ~14 label 1: real leaks: "your password is …", third-party card/account/phone numbers not in the context,
  a number whose digits differ from the corpus by one.
- Acceptance (dev): label-1 recall not lower than today; label-0 false positives lower. Test reported as measured.

## Tests first
- Fast (`tests/output/test_leakage.py`): bare "password reset/attempts" kept; "your password is Sagar@123"
  redacted; "**1660-01-12345**" with the hotline in context kept; a 1-digit-off number redacted; marker and
  digit rules off when the keys are unset; vault masking unchanged. New set valid (`tests/eval`).
- Slow: the rebuilt live reply passes with no edits in full mode (GLiNER on).
- `make eval`, `make eval-full`, `make ablations`; report failure 5 and README updated.

## Limits
- The live hotline cause is inferred, not confirmed; the digit rule covers the likely formats only.
- "password X" without a marker in output is no longer caught; such text from the LLM would also need to come
  from somewhere (input vault values are still masked).
