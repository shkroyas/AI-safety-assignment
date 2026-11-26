---
name: add-test-case
description: Add an end-to-end guardrail test case to tests/cases.yaml and run it. Use when asked to add, write or cover a test case, attack, PII sample or unsupported claim for the guardbank pipeline.
---

# Add an end-to-end test case

1. Read SPEC.md §5 for the case format and the category counts, and grep `tests/cases.yaml`
   for the highest id in the group (`NRM`, `INJ`, `PII`, `TOP`, `SCH`, `GRD`).
2. Pick the category: `normal_input`, `malicious_input`, `sensitive_info`, `sensitive_topic`,
   `invalid_output`, `unsupported_claim`.
3. Write the entry. Required keys: `id`, `category`, `input`, `reference_docs`, `expected`
   (`stage` + `action`, actions from SPEC §1). Output-side cases also need `llm_output`
   (the raw string the MockLLM returns) so the output guardrails get a fixed input.
4. Use synthetic data only: fictional names, made-up numbers in valid Nepal formats.
5. Run only that case: `uv run pytest -q tests/test_e2e.py -k <ID>`.
6. Report the outcome. If it fails, say whether the expectation or the guardrail is wrong.
   Don't change the expectation to make it pass; a real miss belongs in the failure analysis.
