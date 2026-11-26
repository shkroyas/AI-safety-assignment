# Spec delta: feat/e2e-cases

SPEC section: 5. Test case format (`tests/cases.yaml`). ≤40 lines.

## Scope
- `tests/cases.yaml`: 45 cases. SPEC minimum is 40 (8 normal, 8 malicious, 8 sensitive-info, 6 sensitive-topic,
  5 invalid-output, 5 unsupported-claim); we add 2 malicious (poisoned chunk, base64), 2 PII and 1 topic. Synthetic data only.
- `src/guardbank/cases.py`: `load_cases(path)`, `run_case(pipeline, case) -> CaseResult` (`id`, `passed`, `actual`, `reasons`),
  reused by `feat/eval` to fill `actual`/`pass`. `tests/test_e2e.py` runs every case (fast: stubs, hashing, MockLLM).

## Case format (SPEC §5 keys, plus optional checks)
```yaml
- id: INJ-03                      # NRM | INJ | PII | TOP | SCH | GRD
  category: malicious_input       # normal_input | malicious_input | sensitive_info | sensitive_topic | invalid_output | unsupported_claim
  input: "..."
  reference_docs: []              # doc ids; if set, at least one kept chunk must come from one of them
  llm_output: null                # str or list (one per LLM call, last repeats); null = grounded MockLLM
  expected: {stage: input.injection, action: block, outcome: blocked,   # stage + action required, rest optional
             escalate: false, llm_calls: 0, text_contains: [], text_excludes: []}
  known_failure: null             # reason string -> pytest xfail(strict=True)
```
- Stage names are dotted as in SPEC (`input.injection`) and map 1:1 to stage ids (`input_injection`, `rag.chunk_scan` → `chunk_scan`,
  `remediation` stays). `expected.action` is checked on the **first** result of that stage; a stage that never ran fails.
- `llm_output` templates: `{cite}` = first kept chunk id, `{canary}` = this request's canary, `{grounded}` = the MockLLM grounded
  answer text. They let output cases cite real retrieved ids without hard-coding retrieval.
- `actual` = `{stage, action, outcome, escalate, llm_calls}`; `reasons` lists each failed check. Raw text never goes in `actual`.
- A real miss is never "fixed" by editing the expectation: it gets `known_failure` with the cause, and a `fix/*` branch later.

## Live run
- `test_cases_live` (`@pytest.mark.live`): the cases with no `llm_output` against Bedrock via `build_llm(settings, os.environ)`;
  skipped without credentials. Royas runs it with the key loaded (`set -a; . ./.env; set +a`).

## Tests first (`tests/test_cases_format.py` + `tests/test_e2e.py`)
- Format: SPEC counts per category met; ids unique and match category prefix; required keys present; stage names valid;
  output-side categories have `llm_output`; no real-looking secrets (Luhn-valid cards only from the test BIN 4111…).
- Runner: a passing and a failing fake case give the right `passed`/`reasons`; templates filled; `known_failure` → xfail.
- E2E: every case in `cases.yaml` passes (or xfails with its documented reason).

## Out of scope
- Metrics, labeled sets and ablations: `feat/eval`. Fixes for any `known_failure`: `fix/*`.
