# Spec delta: feat/input-injection

SPEC section: 3. Input guardrails (Prompt injection row) + 2. Pipeline order (step 3). One feature only; ≤40 lines.

## Scope
- `input/injection.py`: `InjectionDetector.check(text, decoded=()) -> GuardResult` (stage `"input_injection"`),
  plus `scan(text) -> list[Span]` so `feat/chunk-scan` reuses the same bank on retrieved chunks.
- Classifier hook: `ScoreDetector` protocol (`score(text) -> float`) in `input/detectors.py`, CPU stub returns 0.0.

## Behaviour
- Pruned regex bank, one named pattern per family, case-insensitive, run on the normalizer's `normalized` text
  and each `decoded` string: `IGNORE_INSTRUCTIONS` ("ignore/disregard/forget (all|the|your) previous/above
  instructions|rules"), `ROLE_OVERRIDE` ("you are now", "act as DAN", "developer mode"), `PROMPT_EXTRACTION`
  ("reveal/print/repeat your system prompt|instructions|internal reference"), `FAKE_DELIMITER`
  (`</system>`, `[INST]`, `### system:`), `CANARY_PROBE` (literal `GB-CANARY-` or "canary").
- Each pattern has a weight in YAML; `score = max(regex weight, classifier score)`.
- `detected = score >= tau`; action `BLOCK`, `category` = top pattern name (or `"CLASSIFIER"`), else `ALLOW`.
- On block `details.refusal` = generic message from YAML (never echoes the pattern or the canary);
  `details.matches` = pattern names; spans carry offsets + pattern name.
- Benign look-alikes must pass: "ignore my last message", "forget the card I mentioned", "act as my guarantor?".

## Config (`config/guardrails.yaml`)
```yaml
input:
  injection:
    classifier: stub         # stub | prompt_guard | deberta (models arrive in feat/ml-detectors)
    tau: 0.8
    refusal: "Sorry, I can't help with that request. I can answer questions about Sagarmatha Digital Bank services."
    patterns:                # name -> {regex, weight}; high-confidence families weight 1.0
      IGNORE_INSTRUCTIONS: {regex: "...", weight: 1.0}
      # ROLE_OVERRIDE, PROMPT_EXTRACTION, FAKE_DELIMITER, CANARY_PROBE likewise
```

## Tests first (`tests/input/test_injection.py`, all fast)
- `test_each_family_blocked` (parametrized, ≥2 samples per family), `test_benign_lookalikes_allowed`
  (parametrized), `test_decoded_payload_scanned`, `test_refusal_is_generic`, `test_canary_probe_blocked`,
  `test_classifier_score_over_tau_blocks` (fake ScoreDetector), `test_tau_from_config`, `test_scan_returns_spans`.

## Limits and out of scope
- Semantic, multi-turn and Romanized Nepali attacks: documented, left to the classifier.
- Deferred: real classifier (`feat/ml-detectors`), chunk scan + drop (`feat/chunk-scan`),
  output canary check (`feat/output-leakage`), wiring + audit (`feat/remediation-pipeline`).
