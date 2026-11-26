# Spec delta: feat/chunk-scan

SPEC section: 2. Pipeline order (step 5) + 3. Input guardrails (Prompt injection row: "Poisoned chunk: drop silently, log"). ≤40 lines.

## Scope
- `rag/chunk_scan.py`: `ChunkScanner.filter(hits) -> tuple[list[Hit], GuardResult]` (stage `"chunk_scan"`).
  Each retrieved chunk is normalized (`Normalizer`), then scanned by an `InjectionDetector` whose bank is
  the input bank plus chunk-only patterns. The classifier hook is reused, so `feat/ml-detectors` covers chunks too.

## Behaviour
- A chunk is poisoned when `max(pattern weight, classifier score) >= tau` on its normalized text or decoded strings.
- Poisoned chunks are dropped silently: kept hits keep their order and scores; there is no backfill, so fewer than `top_k` may remain.
- `GuardResult`: `detected` = any dropped, `action` = `DROP_CHUNK` if any dropped else `ALLOW`, `score` = max chunk score,
  `category` = top pattern of the highest-scoring dropped chunk, `details.dropped` = `[{chunk_id, doc_id, matches, score}]`,
  `details.kept` = kept chunk ids. Spans are not returned (chunk offsets mean nothing to the user).
- Chunk-only patterns (chunks are bank-authored policy text, so these are safe there but too strict for user input):
  - `EXTERNAL_EXFIL`: "send/forward/email … to <address>@<domain>", where the domain is not in `allowed_domains`.
  - `CREDENTIAL_REQUEST`: "CVV" within 40 chars of "chat", "send" or "pathau…" (asks the customer to post a CVV).
- Today's corpus: the bank already catches `poisoned-fee-waiver#2` and `poisoned-system-prompt#2`; the new patterns catch
  `poisoned-contact-update#2` (Romanized Nepali plus an outside email). No clean chunk may be dropped.

## Config (`config/guardrails.yaml`)
```yaml
rag:
  chunk_scan:
    tau: 0.8
    allowed_domains: [sagarmatha-digital.example]
    extra_patterns:            # name -> {regex, weight}; added after the input injection bank
      EXTERNAL_EXFIL: {regex: "...", weight: 1.0}
      CREDENTIAL_REQUEST: {regex: "...", weight: 1.0}
```

## Tests first (`tests/rag/test_chunk_scan.py`, all fast)
- `test_all_poisoned_docs_dropped` (each of the 3 poisoned docs loses its injected chunk), `test_no_clean_chunk_dropped`
  (all 117 clean chunks kept), `test_result_shape` (action, details.dropped/kept, order kept), `test_allowed_domain_not_flagged`,
  `test_obfuscated_chunk_caught` (homoglyph/zero-width "ignore previous instructions"), `test_classifier_score_drops_chunk`.

## Limits and out of scope
- Romanized Nepali without an email or CVV cue, and paraphrased poison: left to the classifier and eval. No backfill to top_k.
- Wiring into retrieval and the audit event: `feat/remediation-pipeline`.
