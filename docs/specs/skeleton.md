# Spec delta: feat/skeleton

Scope: the foundation every guardrail builds on. No guardrails yet; the RAG path works
end to end with a real LLM (Bedrock) and a fake one (MockLLM).

## 1. Package and tooling
- `pyproject.toml` (uv, `requires-python >=3.11`), package `src/guardbank/`.
- Runtime deps: `anthropic[bedrock]>=0.60,<2`, `pydantic>=2`, `pyyaml`, `python-dotenv`, `numpy`, `faiss-cpu`.
  Optional extra `ml`: `sentence-transformers` (real embedder; later ML detectors also go here).
- Dev deps: `pytest`, `ruff`.
- pytest markers: `slow` (real models), `live` (calls Bedrock). CI runs `-m "not slow and not live"`.
- `Makefile`: `install`, `test`, `test-all`, `lint`, `eval` (placeholder until feat/eval).

## 2. LLM: Claude Opus 4.6 on Amazon Bedrock
- Model `us.anthropic.claude-opus-4-6-v1` (from `HOSTED_MODEL`), region from `BEDROCK_REGION`.
  Opus 4.6 is served only on Bedrock's `bedrock-runtime` path, so the client is
  `anthropic.AnthropicBedrock(api_key=<BEDROCK_API_KEYS>, aws_region=...)`.
- **SDK pinned `<2`**: SDK 2.x sends API version `2026-10-21`, which Bedrock rejects for
  4.6-and-older models.
- Output: structured outputs (`output_config.format`, JSON schema generated from
  `SupportReply`), adaptive thinking off by default for latency (configurable). The client
  returns the **raw text** so the output guardrails validate it themselves; constrained
  decoding makes real schema failures rare, which is why schema tests use fault injection.
- `LLMClient` protocol: `generate(system: str, messages: list, *, temperature: float|None) -> LLMResponse(text, model, latency_ms, usage)`.
- `MockLLM`: deterministic. Either returns a scripted string (tests and fault injection) or
  builds a grounded `SupportReply` JSON from the top retrieved chunk.
- Secrets read from env only (`.env` via python-dotenv); never logged or written to the audit log.
- Canary: random token per process (`GB-CANARY-<hex>`) placed in the system prompt; exposed for the leakage check later.

## 3. Shared types (`types.py`) — SPEC §1
`Span(start, end, label, text)`, `Action` enum (`allow|redact|block|route|drop_chunk|regenerate|fallback`),
`GuardResult(detected, score, spans, category, action, latency_ms, stage, details)`.
`stage` and `details` are additions so the audit log and eval can say which check fired and why.

## 4. Audit log (`audit.py`) — SPEC §2.8
JSONL; each entry `{ts, request_id, stage, verdict, score, latency_ms, details, prev_hash, hash}`,
`hash = sha256(prev_hash + canonical_json(entry_without_hash))`. `verify(path)` returns the
first broken line or `None`. Raw user text is not logged (only hashes/lengths) to avoid storing PII.

## 5. Corpus and retriever
- `data/corpus/`: 20 synthetic Markdown policy docs (150–400 words, YAML front matter `id`, `title`, `topic`)
  with specific numbers (fees, limits, rates, timelines) for "Sagarmatha Digital Bank" (fictional),
  plus 3 poisoned docs (`poisoned: true`) carrying indirect injections. Interest rates, fees and
  limits are invented; the crisis helpline is not added here (verified later in feat/input-guardrails).
- Chunking: one chunk per doc section (`##`), id `<doc_id>#<n>`.
- `Retriever(top_k=4)`: FAISS inner-product over normalised embeddings. Embedder behind an
  interface: `HashingEmbedder` (fast, deterministic, used in CI) and `SentenceTransformerEmbedder`
  (`BAAI/bge-small-en-v1.5`, `slow`). Model name in YAML.

## 6. Config (`config/guardrails.yaml`)
LLM settings, retriever settings, audit path, and placeholder sections for each guardrail threshold.
Loaded once into a Pydantic `Settings` model; env vars override provider/model/region.

## 7. Minimal pipeline (no guardrails yet)
`Assistant.answer(text) -> (SupportReply|None, raw_text, retrieved_chunks)`: retrieve → build prompt
(system prompt with canary + numbered context) → LLM → parse. Guardrail stages plug in from the next branches.

## 8. CI
`.github/workflows/ci.yml`: on PR and push to main; matrix py3.11/3.12; `uv sync`, `ruff check`,
`ruff format --check`, `pytest -m "not slow and not live"`. After this merges, CI becomes a required
check on `main`.

## 9. Tests written first
- types: GuardResult round-trips to JSON; invalid action rejected.
- audit: chain verifies; editing any line is detected at that line; no raw input stored.
- corpus: 20 normal + 3 poisoned docs load with valid front matter.
- retriever: top-4, ids exist, the fee question ranks the fee doc first (hashing embedder).
- llm: MockLLM deterministic; Bedrock client built with region/model from env without a network call;
  one `live` test calls Bedrock and gets valid JSON.
- pipeline: mock end to end returns a `SupportReply` citing retrieved chunk ids.
