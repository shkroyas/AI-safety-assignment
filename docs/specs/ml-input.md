# Spec delta: feat/ml-input (step 10a of feat/ml-detectors)

SPEC section: 3. Input guardrails (classifier columns of the PII, injection and topic rows). ≤40 lines.

## Scope
- Real models behind the existing protocols in `input/detectors.py`; the stubs stay the YAML default, so CI never downloads.
  - `HFInjectionScorer` (`ScoreDetector`): transformers text-classification; score = probability of the model's positive label.
    Kinds `deberta` = `protectai/deberta-v3-base-prompt-injection-v2` (open), `prompt_guard` = `meta-llama/Llama-Prompt-Guard-2-86M`
    (gated: needs `HF_TOKEN` for an account that accepted Meta's licence). Chunk scan has its own `rag.chunk_scan.classifier`
    (default `stub`): measured, DeBERTa scores 7 of 117 clean chunks ≥ 0.999 vs 1.0 for poisoned ones, so no tau separates them.
  - `GlinerDetector` (`Detector`): `urchade/gliner_multi_pii-v1`, labels person → `PERSON`, location → `LOCATION`; PII backend `gliner`.
  - `EmbedLogRegClassifier` (`TopicClassifier`): `BAAI/bge-small-en-v1.5` embeddings + scikit-learn logistic regression,
    trained at start-up on `data/topics/train.yaml` (synthetic, ~12 per category, paraphrases the keyword rules miss).
- Models load lazily on first use and are cached per (name, device), so stages that pick the same model share one copy.
- `ml` extra gains `transformers`, `gliner`, `scikit-learn`, `sentencepiece`, `protobuf` (GLiNER's mDeBERTa tokenizer).

## Behaviour
- Selection in YAML: `input.injection.classifier: stub|deberta|prompt_guard`, `input.pii.backend: stub|presidio|gliner`,
  `input.topics.classifier: stub|embed_logreg`. Unknown kind → `ValueError` naming the allowed kinds.
- Model ids, labels, thresholds, `max_length: 512` (longer inputs truncated) and `device: auto|cpu|cuda` live in YAML.
- Topic classifier returns `(label, prob)`, `prob` = max class probability; router `tau` decides. `C: 50` (C=4 left a crisis paraphrase at 0.71).
- `data/topics/train.yaml` must not share any text with later eval sets (`feat/eval` asserts no overlap).

## Config (`config/guardrails.yaml`)
```yaml
input:
  injection: {classifier: stub, models: {deberta: {name: ..., positive_label: INJECTION}, prompt_guard: {name: ..., positive_label: LABEL_1}},
              max_length: 512, device: auto}
  pii:       {backend: stub, gliner: {name: urchade/gliner_multi_pii-v1, threshold: 0.5, labels: {person: PERSON, location: LOCATION}}}
  topics:    {classifier: stub, embed_logreg: {embedding_model: BAAI/bge-small-en-v1.5, train_path: data/topics/train.yaml, C: 50.0}}
```

## Tests first
- Fast (`tests/input/test_ml_factories.py`): each kind builds lazily; unknown kind raises; chunk scan's classifier is its own;
  `train.yaml` covers every topic category with ≥10 examples and no duplicates.
- Slow (`tests/input/test_ml_models.py`, `@pytest.mark.slow`): DeBERTa scores attacks > 0.9 and benign < 0.5; Prompt Guard 2
  the same (skipped without `HF_TOKEN`); GLiNER finds a person and a place; topic classifier labels 3 unseen paraphrases.

## Out of scope
- HHEM and sentence-transformer prompt similarity: `feat/ml-output` (10b). Threshold tuning and ablations: `feat/eval`.
