# Spec delta: feat/input-pii

SPEC section: 3. Input guardrails (PII row) + 2. Pipeline order (step 2). One feature only; ≤40 lines.

## Scope
- `input/pii.py`: `PiiRedactor.check(text, vault, decoded=()) -> GuardResult` (stage `"input_pii"`) and
  `PiiVault` (per-session token ↔ value; same value → same token). `Detector` protocol in `input/detectors.py`.

## Behaviour
- Regex + context-word recognizers: `NP_CITIZENSHIP` (e.g. `12-01-75-01234`), `NP_PAN` (9 digits, context
  "PAN"), `NP_PHONE` (`+977`/`977`/bare `98x`/`97x` 10-digit), `ACCOUNT_NO` (10–16 digits, context
  "account"/"a/c"), `CARD` (13–19 digits, Luhn-valid), `OTP` (4–8 digits after "OTP"/"code"/"PIN"),
  `PASSWORD` (token after "password"/"pw is"), `EMAIL`.
- Presidio + spaCy adds `PERSON`/`LOCATION` behind `Detector`; CPU stub (no spans) in fast tests and CI.
- Overlaps: longest span wins, then the label listed first in YAML.
- `text` is the normalizer's `normalized`; each `decoded` string is scanned too (`details.decoded_redacted`).
- `details.redacted` = text with tokens; `details.warning` = "Never share card numbers, OTPs or passwords,
  even with bank staff." when a `never_share` label fired. `span.text` is the token, never the raw value.
- `detected` = any hit, `score` 1.0/0.0, `REDACT`/`ALLOW`, `category` = first label; `vault.restore()` undoes tokens.

## Config (`config/guardrails.yaml`)
```yaml
input:
  pii:
    backend: stub              # stub | presidio (needs new `pii` extra: presidio-analyzer)
    spacy_model: en_core_web_sm
    labels: [CARD, NP_CITIZENSHIP, NP_PAN, ACCOUNT_NO, NP_PHONE, OTP, PASSWORD, EMAIL, PERSON, LOCATION]
    never_share: [CARD, OTP, PASSWORD]
    context_window: 30   # chars before a number searched for context_words (per label, in YAML)
```

## Tests first (`tests/input/test_pii.py`)
- fast: `test_each_nepal_format_redacted` (parametrized), `test_pan_needs_context`, `test_order_id_not_account`,
  `test_card_luhn_only`, `test_never_share_warning`, `test_same_value_same_token`, `test_vault_restore`,
  `test_spans_hold_token_not_value`, `test_decoded_payload_scanned`, `test_clean_text_allow`, `test_config_drives_labels`.
- slow: `test_presidio_person_redacted` (real spaCy model, `pii` extra).

## Limits and out of scope
- Spelled-out/Devanagari digits, Romanized names, PII split across turns: documented, not handled.
- Deferred: GLiNER-PII (`feat/ml-detectors`), wiring (`feat/remediation-pipeline`), output diff (`feat/output-leakage`).
