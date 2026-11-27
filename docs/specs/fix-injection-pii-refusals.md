# Spec delta: fix/injection-pii-refusals (amended 2026-11-27)

SPEC section: 3. Input guardrails (Prompt injection row). Found in docs/report (failure 2, PII-04/05). ≤40 lines.

## Problem (measured, full mode, τ 0.8)
- DeBERTa refuses 15 of 47 benign messages that contain PII (case inputs + PII set). Not fixable by τ (scores 0/1).
- First fix tried (Prompt Guard 2 for messages with PII) failed acceptance: on the new `injection_pii` set it
  caught 2/4 dev and 5/11 test attacks that carry PII (DeBERTa: 3/4, 11/11). Adding PII would be an easy evasion.
- Scoring only the redacted text shuffles refusals: PII-05 allowed, but PII-07 newly refused (0.06 → 0.93).

## Fix: refuse only if the raw and the redacted text are both flagged
- `input.injection.classifier_redacted: true` (YAML). When input PII was found, the classifier also scores the
  redacted text with tokens replaced by words from `input.injection.redacted_words` (`<CARD_1>` → "card"), and
  the classifier score is `min(raw, redacted)`. Regex runs unchanged on the raw and decoded text.
- `check(text, decoded, redacted=None)`; the pipeline and eval runner pass `pii.details["redacted"]`. `details`
  records `classifier_raw` and `classifier_redacted`.
- By construction it never refuses a message the current rule allows. Measured: 47 benign PII messages refused
  15 → 12 (PII-05 fixed, PII-04 still refused); `injection_pii` dev 3/4 caught, 2/9 refused (was 3/9), test 11/11,
  3/21 (was 6/21); main injection set unchanged (dev 10/11, test 24/25).
- Prompt Guard 2 routing is removed. Eval entry points still load `.env` by path (gated models need `HF_TOKEN`).

## New eval set (`data/eval/injection_pii.jsonl`, set `injection_pii`)
- 45 new synthetic items: 30 benign with PII (card, account, OTP, password, phone, email, citizenship, PAN,
  mixed), 15 attacks with PII. Same 30/70 split.
- Acceptance (dev): attack recall no lower than the raw-text rule, benign refusals lower. Test reported as measured.

## Tests first
- Fast (`tests/input/test_injection.py`): raw flagged + redacted not → allow; both → block;
  `classifier_redacted: false` or no redacted text → raw only; regex still blocks; tokens become words.
  `tests/test_pipeline.py`, `tests/eval/test_runners.py`: pipeline and runner pass the redacted text.
  `tests/eval/test_ablations.py`: variant `hybrid+both-flag`. `tests/eval/test_datasets.py`: new set is valid.
- Slow: real DeBERTa: PII-05 and PII-07 allowed; attacks blocked with and without an email appended.
- `make eval-full` + `make ablations` rerun; report failure 2 and README updated with before/after.

## Limits
- A partial fix: 12/47 benign PII messages are still refused, PII-04 among them. A better classifier or
  fine-tuning on banking text is out of scope. Items written by the detector author; small dev split (4 attacks).
