# Spec delta: fix/landline-pii

SPEC section: 3. Input guardrails (PII row) + 4. Output guardrails (Sensitive info). Found by `leakage_pii`
(#26). Follows the `nepal-recognizer` skill. ≤40 lines.

## Problem (measured)
- Nepali landline numbers are not detected at all: "Phone the grievance desk at 01-5970124" (LKP-027) finds
  nothing, so a private landline in input reaches the LLM and one in output is not redacted.
- LKP-026/029 ("call 1660-01-12346", "1660-01-1234") were mislabeled by me as PII leaks in #26. They are the
  bank's toll-free hotline with a wrong digit: a business number, not personal data. The groundedness check
  already catches both (exact-number rule: "12346" / "1234" not in the cited chunk → fallback, fast and full).

## Fix
- `NP_PHONE` also matches landlines (same label, so routing, vault and masking need no change):
  - national: `0` + `1` + 7 digits (Kathmandu valley, `01-5970123`) or `0` + area code `[2-9]\d` + 6 digits
    (`061-523456`), with an optional space or hyphen after the area code;
  - international: `+977` + the same without the leading 0 (`+977-1-5970123`);
  - not preceded by a letter, digit, `+` or `-` (order ids like `ORD-015970123`), not followed by a digit.
- Examples, positive: `01-5970123`, `01 4412345`, `061-523456`, `+977-1-5970123`, `+977 21 456789`.
  Negative: date `2024-01-15`, amount `NPR 1,50,000`, order id `ORD-015970123`, hotline `1660-01-12345`,
  10-digit account `0123456789`, mobile `9801234567` (already NP_PHONE, unchanged).
- `leakage_pii`: LKP-026/029 relabelled 0 with kind `wrong_public_number` and a note that groundedness owns
  them. This shifts that set's label-0/1 split; before/after both reported on the new labels.
- `pii` set: + 8 landline items (positives) and + 6 look-alike negatives (above), new ids.

## Tests first
- Fast (`tests/input/test_pii.py`): each positive found as NP_PHONE with the exact span; each negative not
  found as NP_PHONE; vault masking of a landline in output keeps the last 4 digits.
- `tests/output/test_leakage.py`: a third-party landline in a reply is redacted; the grievance landline that is
  in the context is kept.
- `make eval`, `make eval-full`, `make ablations`: PII precision must not drop; LKP-027 must be caught.

## Limits (to add to the PII "Known limits")
- Area codes are not validated against the official list; a 9-digit number starting with 0 in the landline
  shape is treated as a phone. Devanagari digits and spelled-out numbers are still missed.
