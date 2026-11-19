def test_settings_load_defaults(settings):
    assert settings.retriever.top_k == 4
    assert settings.llm.provider in {"bedrock", "mock"}
    assert settings.llm.model


def test_env_overrides_provider_model_region(root):
    from guardbank.config import load_settings

    s = load_settings(
        root / "config" / "guardrails.yaml",
        env={
            "HOSTED_PROVIDER": "bedrock",
            "HOSTED_MODEL": "us.anthropic.claude-opus-4-6-v1",
            "BEDROCK_REGION": "us-east-1",
        },
    )
    assert s.llm.provider == "bedrock"
    assert s.llm.model == "us.anthropic.claude-opus-4-6-v1"
    assert s.llm.region == "us-east-1"


def test_secrets_never_in_settings(root):
    from guardbank.config import load_settings

    s = load_settings(root / "config" / "guardrails.yaml", env={"BEDROCK_API_KEYS": "secret-xyz"})
    assert "secret-xyz" not in s.model_dump_json()
