"""HTTP API: POST /chat runs the guarded pipeline, returns a guardrail report (api-mcp spec).

Run with `make serve`. `serve_app` is a uvicorn factory: only the server process loads `.env`,
so importing this module (e.g. in tests) never pulls credentials into the environment.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from guardbank.config import DEFAULT_CONFIG, Settings, load_settings
from guardbank.evaluation.runners import models_used, settings_for
from guardbank.pipeline import Pipeline, Session
from guardbank.rag.llm import build_llm
from guardbank.remediation import public_report

log = logging.getLogger("guardbank.api")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    reply: str
    outcome: str
    escalate: bool
    citations: list[str]
    guardrail_report: list[dict[str, Any]]


def create_app(pipeline: Any = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings(DEFAULT_CONFIG, env=os.environ)
    api_cfg = settings.api
    mode = os.environ.get("GUARDBANK_MODE") or api_cfg.get("mode", "fast")
    effective = settings_for(settings, mode)
    app = FastAPI(title="guardbank", description="Guardrailed support assistant (fictional bank)")
    app.state.pipeline = pipeline
    app.state.sessions: OrderedDict[str, Session] = OrderedDict()

    def get_pipeline() -> Any:
        if app.state.pipeline is None:
            app.state.pipeline = Pipeline.from_settings(
                effective, llm=build_llm(effective, os.environ)
            )
        return app.state.pipeline

    def get_session(session_id: str | None) -> tuple[str, Session]:
        sessions = app.state.sessions
        if session_id and session_id in sessions:
            sessions.move_to_end(session_id)
            return session_id, sessions[session_id]
        new_id = uuid.uuid4().hex
        sessions[new_id] = Session()
        while len(sessions) > api_cfg.get("max_sessions", 1000):
            sessions.popitem(last=False)
        return new_id, sessions[new_id]

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> Any:
        if len(req.message) > api_cfg.get("max_message_chars", 4000):
            raise HTTPException(status_code=422, detail="message too long")
        session_id, session = get_session(req.session_id)
        try:
            result = get_pipeline().run(req.message, session)
        except Exception as exc:  # never leak internals (keys, hosts) to the client
            log.error("pipeline failed (%s)", type(exc).__name__)
            return JSONResponse(status_code=503, content={"detail": "assistant unavailable"})
        return ChatResponse(
            request_id=result.request_id,
            session_id=session_id,
            reply=result.text,
            outcome=result.outcome,
            escalate=result.escalate,
            citations=result.reply.citations if result.reply else [],
            guardrail_report=public_report(result.stages),
        )

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        p = request.app.state.pipeline
        llm = getattr(p.llm, "model", "unknown") if p is not None else effective.llm.provider
        return {"status": "ok", "mode": mode, "llm": llm, "models": models_used(effective)}

    return app


def serve_app() -> FastAPI:
    """uvicorn factory for `make serve`: the server process loads `.env` itself."""
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    return create_app()
