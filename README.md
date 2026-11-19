# guardbank

Input and output guardrails for a customer-support RAG assistant of a fictional bank,
"Sagarmatha Digital Bank". Built for the Trustworthy AI Assignment 1.

Status: in development. The design is in [SPEC.md](SPEC.md). Guardrails, evaluation results
and the report are added feature by feature.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # core install
uv sync --extra ml      # + real embedding / classifier models
cp .env.example .env    # then fill in Bedrock and Hugging Face credentials
```

Without credentials, the assistant runs on `MockLLM`, a deterministic stand-in.

## LLM

Claude Opus 4.6 on Amazon Bedrock (`us.anthropic.claude-opus-4-6-v1`), called with the
`AnthropicBedrock` client and an Amazon Bedrock API key. Opus 4.6 is served on Bedrock's
`bedrock-runtime` path, which rejects the API version sent by `anthropic` SDK 2.x, so the SDK
is pinned below 2. Replies use structured outputs with the `SupportReply` JSON schema.

## Tests

```bash
make test        # fast: mock LLM, hashing embedder (what CI runs)
make test-all    # + slow (real models) and live (calls Bedrock) tests
make lint
```
