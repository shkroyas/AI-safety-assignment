"""Load config/guardrails.yaml into typed settings. Secrets are never part of Settings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "guardrails.yaml"


class LLMSettings(BaseModel):
    provider: Literal["mock", "bedrock"] = "mock"
    model: str
    region: str = "us-east-1"
    max_tokens: int = 2048
    timeout_s: float = 60
    max_retries: int = 2
    structured_output: bool = True


class RetrieverSettings(BaseModel):
    top_k: int = 4
    embedder: Literal["hashing", "sentence-transformers"] = "hashing"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    hashing_dim: int = 4096


class CorpusSettings(BaseModel):
    path: str = "data/corpus"


class AuditSettings(BaseModel):
    path: str = "logs/audit.jsonl"


class Settings(BaseModel):
    model_config = ConfigDict(extra="allow")

    llm: LLMSettings
    retriever: RetrieverSettings = RetrieverSettings()
    corpus: CorpusSettings = CorpusSettings()
    audit: AuditSettings = AuditSettings()
    input: dict[str, Any] = {}
    output: dict[str, Any] = {}

    def resolve(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else ROOT / p


_ENV_OVERRIDES = {
    "HOSTED_PROVIDER": "provider",
    "HOSTED_MODEL": "model",
    "BEDROCK_REGION": "region",
}


def load_settings(
    path: str | Path = DEFAULT_CONFIG, env: Mapping[str, str] | None = None
) -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for var, key in _ENV_OVERRIDES.items():
        if env and env.get(var):
            data["llm"][key] = env[var]
    return Settings.model_validate(data)
