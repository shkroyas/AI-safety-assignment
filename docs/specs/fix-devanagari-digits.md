# Spec delta: fix/devanagari-digits

SPEC section: 2. Pipeline order (step 1, normalizer) + 3. Input guardrails (PII). From
EVALUATION_RECOMMENDATIONS.md P1-4 (first half), reproduced. ≤40 lines.

## Problem (reproduced)
- A mobile number written in Devanagari digits, "Call me on ९८४१२३४५६७ please.", is not detected: `NP_PHONE`
  starts with the literal ASCII digits 9 and 7/8. Account, citizenship, OTP, PAN and card numbers in Devanagari
  happen to be found, because Python's `\d` also matches Devanagari digits, so behaviour is inconsistent.
- Nepali users write numbers in Devanagari; the SPEC lists "Devanagari digits" as a known PII gap.

## Fix
- `input.normalizer.digits` (YAML): a mapping ० → 0 … ९ → 9, applied after NFKC. Every later stage (PII,
  injection, topics, retrieval, the LLM prompt) sees ASCII digits. The normalizer reports the change as
  `digits` in `changes` and keeps it a non-blocking stage.
- The LLM receives the redacted ASCII form, as for any other number.

## Tests first
- Fast (`tests/input/test_normalizer.py`): "९८४१२३४५६७" normalizes to "9841234567"; text without Devanagari
  digits is unchanged; `digits` reported in `changes`.
- Fast (`tests/input/test_pii.py`): the Devanagari phone, account, citizenship, OTP and card examples are each
  found with the same label as their ASCII form.
- `pii` set: + 4 items with Devanagari numbers (phone, account, OTP, citizenship) and 1 negative (a Devanagari
  year in a date-free sentence, "२०८१ सालको बजेट").
- `make eval`, `make eval-full`, `make ablations`; SPEC PII "known limits" and report updated.

## Limits
- Only digits are mapped; spelled-out Nepali numbers ("नौ आठ चार…") and Devanagari words are not handled.
- `lakh` / `crore` grounding (the second half of P1-4) is a separate change.
