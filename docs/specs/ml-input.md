# Spec delta: feat/ml-input (step 10a of feat/ml-detectors)

SPEC section: 3. Input guardrails (classifier columns of the PII, injection and topic rows). ≤40 lines.

## Scope
- Real models behind the existing protocols in `input/detectors.py`; the stubs stay the YAML default, so CI never downloads.
  - `HFInjectionScorer` (`ScoreDetector`): transformers text-classification; score = probability of the model's positive label.
    Kinds `deberta` = `protectai/deberta-v3-base-prompt-injection-v2` (open), `prompt_guard` = `meta-llama/Llama-Prompt-Guard-2-86M`
    (gated: needs `HF_TOKEN` in the environment for an account that accepted Meta's licence). Used by input injection and chunk scan.
  - `GlinerDetector` (`Detector`): `urchade/gliner_multi_pii-v1`, labels person → `PERSON`, location → `LOCATION`; PII backend `gliner`.
  - `EmbedLogRegClassifier` (`TopicClassifier`): `BAAI/bge-small-en-v1.5` embeddings + scikit-learn logistic regression,
    trained at start-up on `data/topics/train.yaml` (synthetic, ~12 per category, paraphrases the keyword rules miss).
- Models load lazily on first use and are cached per (name, device), so injection and chunk scan share one copy.
- Dependencies: `ml` extra gains `transformers`, `gliner`, `scikit-learn` (torch via sentence-transformers).

## Behaviour
- Selection in YAML: `input.injection.classifier: stub|deberta|prompt_guard`, `input.pii.backend: stub|presidio|gliner`,
  `input.topics.classifier: stub|embed_logreg`. Unknown kind → `ValueError` naming the allowed kinds.
- Model ids, positive labels, max length, thresholds and `device: auto|cpu|cuda` (auto = cuda when available) live in YAML.
- Inputs longer than the model limit are truncated (`max_length: 512`); limit documented.
- Topic classifier returns `(label, prob)` with `prob` = max class probability; the router's `tau` still decides.
- `data/topics/train.yaml` must not share any text with later eval sets (`feat/eval` asserts no overlap).

## Config (`config/guardrails.yaml`)
```yaml
input:
  injection: {classifier: stub, models: {deberta: {name: ..., positive_label: INJECTION}, prompt_guard: {name: ..., positive_label: LABEL_1}},
              max_length: 512, device: auto}
  pii:       {backend: stub, gliner: {name: urchade/gliner_multi_pii-v1, threshold: 0.5, labels: {person: PERSON, location: LOCATION}}}
  topics:    {classifier: stub, embed_logreg: {embedding_model: BAAI/bge-small-en-v1.5, train_path: data/topics/train.yaml, C: 4.0}}
```

## Tests first
- Fast (`tests/input/test_ml_factories.py`): each kind builds the right class without loading weights; unknown kind raises;
  `train.yaml` covers every topic category with ≥10 examples and no duplicates.
- Slow (`tests/input/test_ml_models.py`, `@pytest.mark.slow`): DeBERTa scores attacks > 0.9 and benign < 0.5; Prompt Guard 2
  the same (skipped without `HF_TOKEN`); GLiNER finds a person and a place; topic classifier labels 3 unseen paraphrases.

## Out of scope
- HHEM and sentence-transformer prompt similarity: `feat/ml-output` (10b). Threshold tuning and ablations: `feat/eval`.
