from guardbank.assistant import Assistant
from guardbank.rag.llm import MockLLM


def test_mock_end_to_end_returns_reply_citing_retrieved_chunks(settings, tmp_path):
    settings.audit.path = str(tmp_path / "audit.jsonl")
    assistant = Assistant.from_settings(settings, llm=MockLLM())
    result = assistant.answer("What is the daily ATM cash withdrawal limit?")
    assert result.reply is not None
    retrieved = {h.chunk.id for h in result.retrieved}
    assert set(result.reply.citations) <= retrieved
    assert result.reply.citations


def test_system_prompt_contains_canary_and_numbered_context(settings, tmp_path):
    settings.audit.path = str(tmp_path / "audit.jsonl")
    llm = MockLLM()
    assistant = Assistant.from_settings(settings, llm=llm)
    assistant.answer("How do I block my card?")
    system = llm.calls[0]["system"]
    assert assistant.canary in system
    assert "[card-blocking#" in system


def test_unparseable_output_gives_none_reply_and_raw_text(settings, tmp_path):
    settings.audit.path = str(tmp_path / "audit.jsonl")
    assistant = Assistant.from_settings(settings, llm=MockLLM(scripted=["Sure! {broken"]))
    result = assistant.answer("hello")
    assert result.reply is None
    assert result.raw_text == "Sure! {broken"
