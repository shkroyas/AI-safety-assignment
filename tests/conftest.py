from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def settings():
    from guardbank.config import load_settings

    return load_settings(ROOT / "config" / "guardrails.yaml", env={})
