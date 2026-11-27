"""LLM clients: Claude Opus 4.6 on Amazon Bedrock, and a deterministic MockLLM.

Both return the raw response text; the output guardrails parse and validate it.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from guardbank.config import Settings


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: float
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str | None = None


class LLMClient(Protocol):
    def generate(
        self, system: str, messages: list[dict], *, temperature: float | None = None
    ) -> LLMResponse: ...


def support_reply_schema() -> dict[str, Any]:
    import anthropic

    from guardbank.output.schema import SupportReply

    return anthropic.transform_schema(SupportReply)


class BedrockLLM:
    """Claude on Bedrock's bedrock-runtime path (Opus 4.6 is not on bedrock-mantle)."""

    def __init__(
        self,
        *,
        model: str,
        region: str,
        api_key: str,
        max_tokens: int,
        timeout_s: float = 60,
        max_retries: int = 2,
        structured_output: bool = True,
    ):
        from anthropic import AnthropicBedrock

        self.model = model
        self.max_tokens = max_tokens
        self.structured_output = structured_output
        self.client = AnthropicBedrock(
            api_key=api_key, aws_region=region, timeout=timeout_s, max_retries=max_retries
        )

    def __repr__(self) -> str:
        return f"BedrockLLM(model={self.model!r}, region={self.client.aws_region!r})"

    def generate(
        self, system: str, messages: list[dict], *, temperature: float | None = None
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {}
        if self.structured_output:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": support_reply_schema()}
            }
        if temperature is not None:
            # SDK 1.x dropped the keyword; Opus 4.6 on API version 2023-06-01 still accepts it.
            kwargs["extra_body"] = {"temperature": temperature}
        start = time.perf_counter()
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            **kwargs,
        )
        latency = (time.perf_counter() - start) * 1000
        text = "".join(b.text for b in message.content if b.type == "text")
        return LLMResponse(
            text=text,
            model=self.model,
            latency_ms=latency,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
            stop_reason=message.stop_reason,
        )


_CONTEXT_BLOCK = re.compile(r"^\[([a-z0-9-]+#\d+)\]\s*(.*?)(?=\n\n\[|\Z)", re.MULTILINE | re.DOTALL)


class MockLLM:
    """Deterministic stand-in for tests, CI and fault injection.

    With `scripted`, returns those strings in order (then repeats the last one).
    Otherwise answers with the first sentence of the first context section.
    """

    model = "mock"

    def __init__(self, scripted: list[str] | None = None):
        self.scripted = list(scripted or [])
        self.calls: list[dict[str, Any]] = []

    def generate(
        self, system: str, messages: list[dict], *, temperature: float | None = None
    ) -> LLMResponse:
        self.calls.append({"system": system, "messages": messages, "temperature": temperature})
        if self.scripted:
            text = self.scripted.pop(0) if len(self.scripted) > 1 else self.scripted[0]
        else:
            text = self._grounded(system)
        return LLMResponse(text=text, model=self.model, latency_ms=0.0)

    @staticmethod
    def _grounded(system: str) -> str:
        match = _CONTEXT_BLOCK.search(system)
        lines = []
        if match:
            lines = [
                re.sub(r"^\d+[.)]\s+", "", ln.strip(" -*").strip())
                for ln in match.group(2).splitlines()
                if ln.strip() and not ln.lstrip().startswith(("#", "|"))
            ]
        if not lines:
            reply = {
                "answer": "I don't have reliable information on that.",
                "citations": [],
                "intent": "other",
                "confidence": 0.0,
                "escalate": True,
                "refusal_reason": "no_context",
            }
        else:
            first = re.split(r"(?<=[.!?])\s", lines[0], maxsplit=1)[0]
            reply = {
                "answer": first,
                "citations": [match.group(1)],
                "intent": "other",
                "confidence": 0.8,
                "escalate": False,
                "refusal_reason": None,
            }
        return json.dumps(reply)


def build_llm(settings: Settings, env: Mapping[str, str]) -> LLMClient:
    """Bedrock when configured and a key is present; otherwise MockLLM."""
    provider = env.get("HOSTED_PROVIDER") or settings.llm.provider
    api_key = env.get("BEDROCK_API_KEYS", "").split(",")[0].strip()
    if provider == "bedrock" and api_key:
        return BedrockLLM(
            model=settings.llm.model,
            region=settings.llm.region,
            api_key=api_key,
            max_tokens=settings.llm.max_tokens,
            timeout_s=settings.llm.timeout_s,
            max_retries=settings.llm.max_retries,
            structured_output=settings.llm.structured_output,
        )
    return MockLLM()
