# Spec delta: feat/output-schema

SPEC section: 4. Output guardrails (response schema + Schema row). ≤40 lines.

## Scope
- `output/schema.py`: keep `SupportReply`; add `SchemaGuard.check(raw, retrieved_ids) -> GuardResult` (stage `"output_schema"`).
- `output/faults.py`: named fault injectors `FAULTS: dict[name, (fn(valid_dict) -> raw str, expected category)]`,
  reused by tests now and by `MockLLM(scripted=...)` in the eval later.

## Behaviour
- Order: optional code-fence strip → JSON parse → Pydantic (`SupportReply`) → citation-exists. First failure wins.
- Categories: `JSON_INVALID` (not JSON, truncated, not an object), `SCHEMA_INVALID` (missing/extra field, wrong type,
  bad enum, out of range, answer length), `RULE_VIOLATION` (empty citations without `refusal_reason`, complaint without
  `escalate`), `CITATION_MISSING` (a cited id not in `retrieved_ids`).
- Invalid: `detected=True`, `score=1.0`, `action=REGENERATE` (remediation decides retries/fallback),
  `details.errors` = short messages (field + reason, no echo of the raw text), `details.feedback` = one string
  to send back to the model on regenerate.
- Valid: `ALLOW`, `details.reply` = the parsed `SupportReply`; `details.fenced` = whether a fence was stripped.
- A refusal (`refusal_reason` set, no citations) is valid; citations are still checked when present.

## Config (`config/guardrails.yaml`)
```yaml
output:
  schema:
    strip_code_fence: true   # accept one ```json ... ``` wrapper around the object
```

## Faults (each → expected category)
`not_json`, `truncated`, `json_array` → JSON_INVALID; `missing_field`, `extra_field`, `bad_intent`, `confidence_high`,
`confidence_negative`, `wrong_type`, `empty_answer`, `answer_too_long` → SCHEMA_INVALID; `empty_citations`,
`complaint_no_escalate` → RULE_VIOLATION; `unknown_citation` → CITATION_MISSING.

## Tests first (`tests/output/test_schema.py`, all fast)
- `test_valid_reply_allowed`, `test_refusal_without_citations_allowed`, `test_fault_detected` (parametrized over
  `FAULTS`: detected, REGENERATE, expected category), `test_errors_do_not_echo_raw`, `test_feedback_names_field`,
  `test_code_fence_stripped`, `test_fence_strip_off_by_config`, `test_mockllm_scripted_fault_roundtrip`.

## Limits and out of scope
- Valid structure says nothing about truth (groundedness: `feat/output-groundedness`).
- Retry loop and safe fallback: `feat/remediation-pipeline`. The SPEC's 1200-char limit stays in the model, not in YAML.
