import json

import pytest

from guardbank.rag.llm import BedrockLLM, MockLLM, build_llm


def test_mock_scripted_output_is_returned_verbatim():
    llm = MockLLM(scripted=["not json at all"])
    assert llm.generate("sys", [{"role": "user", "content": "hi"}]).text == "not json at all"


def test_mock_scripted_outputs_are_consumed_in_order():
    llm = MockLLM(scripted=["a", "b"])
    assert [llm.generate("s", []).text for _ in range(2)] == ["a", "b"]


def test_mock_default_builds_grounded_reply_from_context():
    system = "...\n[atm-cards#1] Daily ATM withdrawal limit is NPR 100,000.\n..."
    out = MockLLM().generate(system, [{"role": "user", "content": "atm limit?"}])
    data = json.loads(out.text)
    assert data["citations"] == ["atm-cards#1"]
    assert "100,000" in data["answer"]


def test_mock_is_deterministic():
    system = "[fees#1] Cheque book costs NPR 250."
    a = MockLLM().generate(system, []).text
    b = MockLLM().generate(system, []).text
    assert a == b


def test_bedrock_client_configured_without_network(settings):
    llm = BedrockLLM(
        model="us.anthropic.claude-opus-4-6-v1",
        region="us-east-1",
        api_key="test-token",
        max_tokens=1024,
    )
    assert llm.model == "us.anthropic.claude-opus-4-6-v1"
    assert llm.client.aws_region == "us-east-1"


def test_build_llm_uses_mock_without_credentials(settings):
    assert isinstance(build_llm(settings, env={}), MockLLM)


def test_bedrock_api_key_never_in_repr():
    llm = BedrockLLM(model="m", region="us-east-1", api_key="super-secret-token", max_tokens=10)
    assert "super-secret-token" not in repr(llm)


@pytest.mark.live
def test_bedrock_live_returns_valid_json(settings):
    import os

    from dotenv import load_dotenv

    from guardbank.output.schema import SupportReply

    load_dotenv()
    llm = build_llm(settings, env=dict(os.environ))
    assert isinstance(llm, BedrockLLM)
    system = (
        "You are a bank support assistant. Answer only from the context.\n"
        "[atm-cards#1] The daily ATM withdrawal limit is NPR 100,000."
    )
    out = llm.generate(system, [{"role": "user", "content": "What is the ATM limit?"}])
    reply = SupportReply.model_validate_json(out.text)
    assert "atm-cards#1" in reply.citations


def test_mock_strips_list_marker_from_context_line():
    """docs/specs/fix-claim-splitting.md: the answer is the step, not "1."."""
    system = (
        "...\n[fraud-and-scams#2] 1. Block your card immediately in the SDB app. 2. Call us.\n..."
    )
    data = json.loads(MockLLM().generate(system, []).text)
    assert data["answer"] == "Block your card immediately in the SDB app."
