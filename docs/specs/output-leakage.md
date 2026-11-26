# Spec delta: feat/output-leakage

SPEC section: 4. Output guardrails (Sensitive info row + policy rows 4–6). ≤40 lines.

## Scope
- `output/leakage.py`: `LeakageChecker.check(answer, vault, canary, context) -> GuardResult` (stage `"output_leakage"`).
- Small public hooks: `PiiRedactor.find(text) -> list[(start, end, label)]`, `PiiVault.has_value(value)` and `PiiVault.value_of(token)`.

## Behaviour (worst first; first BLOCK wins, PII findings combine)
1. `CANARY_LEAK`: the canary, or any `GB-CANARY-` prefix, in the answer (case-insensitive, after NFKC + zero-width strip) → `BLOCK`, severity `high`.
2. `PROMPT_LEAK`: max cosine between any answer sentence and any instruction sentence of `SYSTEM_TEMPLATE`
   (the part before `CONTEXT:`, sentences of ≥4 words, canary removed) `>= tau_prompt` → `BLOCK`, severity `high`.
   Embedder = `retriever.embedder` (hashing in CI): clean corpus sentences max 0.63, verbatim prompt lines 0.87–1.0 → 0.75.
3. PII: `PiiRedactor.find` on the answer, plus vault tokens (`<NP_PHONE_1>`) the model echoed. For each hit:
   - value appears verbatim in `context` (bank-published contact data) → `PUBLIC`, left as is;
   - token, or value in this user's vault → `OWN_PII` → partial mask (`******7890`, `r***@domain`); CARD/OTP/PASSWORD → `[hidden]`;
   - otherwise → `THIRD_PARTY_PII` → replaced by `[redacted <LABEL>]`, severity `medium`.
   Any PII change → `REDACT`; category `THIRD_PARTY_PII` if any, else `OWN_PII` (severity `low`).
- Nothing found → `ALLOW`. `details.text` = safe answer (None on BLOCK); `details.incidents` = `[{type, label}]`;
  `details.severity`; `details.prompt_similarity`. Raw PII and the canary never appear in details or spans.

## Config (`config/guardrails.yaml`)
```yaml
output:
  leakage:
    canary_prefix: "GB-CANARY-"
    tau_prompt: 0.75
    keep_last: 4
    full_hide: [CARD, OTP, PASSWORD]
```

## Tests first (`tests/output/test_leakage.py`, all fast)
- `test_clean_answer_allowed`, `test_canary_blocked` (exact, upper-case, zero-width-split), `test_any_canary_prefix_blocked`,
  `test_prompt_verbatim_blocked`, `test_no_clean_corpus_sentence_flagged` (all clean corpus sentences < tau),
  `test_third_party_pii_redacted`, `test_own_pii_partially_masked`, `test_own_token_restored_masked`, `test_never_share_fully_hidden`,
  `test_public_context_value_kept`, `test_details_never_hold_raw_values`.

## Limits and out of scope
- Paraphrased prompt leaks score low with hashing (0.43 for a summarised rule list); sentence-transformers in `feat/ml-detectors`.
- Invented-but-realistic PII looks third-party (redacted, which is the safe side). Incident logging: `feat/remediation-pipeline`.
