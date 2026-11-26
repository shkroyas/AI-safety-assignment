# Spec delta: feat/api-mcp

SPEC section: 9. Claude Code development layer (MCP row) + plan item 8 (FastAPI `POST /chat` with `guardrail_report`). ≤40 lines.

## Scope
- `src/guardbank/api.py`: `create_app(pipeline=None) -> FastAPI`; module-level `app` builds its pipeline lazily on first request.
  Run: `make serve` (`uvicorn guardbank.api:app`). The LLM comes from `build_llm(settings, os.environ)`; `.env` is loaded by
  the server process itself (python-dotenv), never read by Claude Code.
- `src/guardbank/mcp_server.py`: Python `mcp` SDK 2.x (`MCPServer`, formerly `FastMCP`; stdio) exposing `check_input`, `check_output`, `run_case`;
  registered as `guardbank` in `.mcp.json` (`uv run --quiet python -m guardbank.mcp_server`).
- Dependencies (core, so CI tests them): `fastapi`, `uvicorn`, `mcp`.

## API
- `POST /chat` `{message: str (1..api.max_message_chars), session_id?: str}` → `{request_id, session_id, reply, outcome, escalate,
  citations, guardrail_report: [{stage, action, detected, score, category, latency_ms, reason?}]}`.
  The report carries no detail text (no raw input, no model text, no PII); `reason` only for the `remediation` stage.
- Sessions: in-memory map `session_id → Session` (per-session PII vault), new id (uuid4 hex) when absent or unknown,
  capped at `api.max_sessions` (oldest dropped).
- `GET /health` → `{status: "ok", mode, llm, models}`. Invalid body → 422 (FastAPI). A pipeline exception → 503
  `{"detail": "assistant unavailable"}`, logged with request id only.
- Mode: `api.mode` in YAML (`fast` default), overridable by env `GUARDBANK_MODE=full` (all ML models, `ml` extra).

## MCP tools (results are JSON; detail text keys removed as in the audit log)
- `check_input(text)` → stages normalizer → PII → injection → topics with a fresh session, plus `redacted_text` and `verdict`
  (`block` | `route` | `allow`, from the first stage that stops the pipeline).
- `check_output(raw_llm_output, retrieved: {chunk_id: text}, canary = "")` → schema, then leakage and groundedness on a
  schema-valid reply; `verdict` = worst action.
- `run_case(case_id)` → `CaseResult` for that id from `tests/cases.yaml` (fast settings, MockLLM / scripted output).

## Config (`config/guardrails.yaml`)
`api: {mode: fast, max_message_chars: 4000, max_sessions: 1000}`

## Tests first (`tests/test_api.py`, `tests/test_mcp_server.py`, fast, TestClient + direct tool calls)
- API: benign → answered + full stage list; injection → blocked, LLM not called; PII → reply and report never contain the
  number; same `session_id` reuses the vault; crisis → 1166, escalate; empty / too-long message → 422; `/health`;
  pipeline error → 503 generic; session cap evicts the oldest.
- MCP: the server lists exactly the 3 tools; `check_input` blocks an injection and redacts a phone; `check_output` flags a
  canary leak and a schema fault; `run_case("INJ-01")` passes; unknown case id → error message, not a crash.

## Live check (Royas, with keys): `curl` benign / injection / PII / crisis against `make serve`; `/mcp` lists `guardbank`.
