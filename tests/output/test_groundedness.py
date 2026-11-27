"""Groundedness check (SPEC §4 groundedness row, docs/specs/output-groundedness.md)."""

import copy

import pytest

from guardbank.output.groundedness import GroundednessChecker, split_claims
from guardbank.output.schema import SupportReply
from guardbank.types import Action, GuardResult

CHUNKS = {
    "atm-cards#1": (
        "The daily ATM withdrawal limit is NPR 25,000. "
        "Each withdrawal at another bank's ATM costs NPR 25."
    ),
    "fees#2": (
        "Interest on savings is 2.5% per year, paid quarterly. The annual card fee is NPR 500."
    ),
}

GOOD = "The daily ATM withdrawal limit is NPR 25,000."
INVENTED = "Premium members also receive free airport lounge access worldwide."
INVENTED_2 = "Gold customers get a dedicated relationship manager on weekends."


def reply(answer: str, citations=("atm-cards#1",), **kw) -> SupportReply:
    data = {
        "answer": answer,
        "citations": list(citations),
        "intent": "cards",
        "confidence": 0.9,
        "escalate": False,
        "refusal_reason": None,
    }
    data.update(kw)
    return SupportReply.model_validate(data)


@pytest.fixture
def checker(settings) -> GroundednessChecker:
    return GroundednessChecker.from_settings(settings)


class FakeScorer:
    def __init__(self, value: float) -> None:
        self.value = value

    def score(self, claim: str, evidence: str) -> float:
        return self.value


def test_claim_split():
    text = "The limit is NPR 25,000. Interest is 2.5% a year!\nCall us? Ok"
    assert split_claims(text) == [
        "The limit is NPR 25,000.",
        "Interest is 2.5% a year!",
        "Call us?",
        "Ok",
    ]


def test_grounded_reply_allowed(checker):
    r = checker.check(reply(GOOD), CHUNKS)
    assert isinstance(r, GuardResult)
    assert r.stage == "output_groundedness"
    assert r.action == Action.ALLOW
    assert r.detected is False
    assert r.details["support"] == 1.0
    assert r.score == 0.0
    (claim,) = r.details["claims"]
    assert claim["supported"] is True and claim["numbers_missing"] == []


def test_wrong_amount_number_mismatch(checker):
    answer = GOOD + " Each withdrawal at another bank's ATM costs NPR 30."
    r = checker.check(reply(answer), CHUNKS)
    assert r.action == Action.REGENERATE
    assert r.category == "NUMBER_MISMATCH"
    assert r.details["unsupported"] == [1]
    assert r.details["claims"][1]["numbers_missing"] == ["30"]
    assert r.details["support"] == 0.5
    assert r.score == 0.5


@pytest.mark.parametrize(
    ("claim", "evidence"),
    [
        ("The limit is NPR 25000 per day.", "The limit is NPR 25,000 per day."),
        ("Savings interest is 2.5 percent.", "Savings interest is 2.5% per year."),
        ("Savings interest is 2 per cent.", "Savings interest is 2% per year."),
        ("The card fee is Rs. 500.", "The card fee is NPR 500."),
        ("The account opened on 2024-01-15.", "The account opened on 15 January 2024."),
        ("The account opened on January 15, 2024.", "The account opened on 2024-01-15."),
    ],
)
def test_number_formats_normalised(checker, claim, evidence):
    r = checker.check(reply(claim, citations=["x#0"]), {"x#0": evidence})
    (c,) = r.details["claims"]
    assert c["numbers_missing"] == []
    assert c["supported"] is True
    assert r.action == Action.ALLOW


def test_invented_sentence_unsupported(checker):
    r = checker.check(reply(f"{GOOD} {INVENTED}"), CHUNKS)
    assert r.action == Action.REGENERATE
    assert r.category == "UNSUPPORTED_CLAIM"
    assert r.detected is True
    assert r.details["unsupported"] == [1]


def test_mostly_invented_fallback(checker):
    r = checker.check(reply(f"{GOOD} {INVENTED} {INVENTED_2}"), CHUNKS)
    assert r.action == Action.FALLBACK
    assert r.details["support"] == pytest.approx(1 / 3)


def test_no_citations_fallback(checker):
    empty = SupportReply.model_construct(**reply(GOOD).model_dump() | {"citations": []})
    r = checker.check(empty, CHUNKS)
    assert r.action == Action.FALLBACK
    assert r.category == "NO_CITATIONS"
    r = checker.check(reply(GOOD, citations=["not-retrieved#3"]), CHUNKS)
    assert r.category == "NO_CITATIONS"


def test_refusal_skipped(checker):
    refusal = reply(INVENTED, citations=[], refusal_reason="no_context", confidence=0.0)
    r = checker.check(refusal, CHUNKS)
    assert r.action == Action.ALLOW
    assert r.details["skipped"] == "refusal"


def test_only_cited_chunks_are_evidence(checker):
    answer = "The annual card fee is NPR 500."
    assert checker.check(reply(answer, citations=["fees#2"]), CHUNKS).action == Action.ALLOW
    r = checker.check(reply(answer, citations=["atm-cards#1"]), CHUNKS)
    assert r.action == Action.FALLBACK


def test_number_check_off_by_config(settings):
    cfg = copy.deepcopy(settings.output["groundedness"])
    wrong = reply("The daily ATM withdrawal limit is NPR 50,000.")
    assert GroundednessChecker(cfg).check(wrong, CHUNKS).action == Action.FALLBACK
    cfg["number_check"] = False
    assert GroundednessChecker(cfg).check(wrong, CHUNKS).action == Action.ALLOW


def test_scorer_swappable(settings):
    cfg = settings.output["groundedness"]
    assert (
        GroundednessChecker(cfg, scorer=FakeScorer(0.0)).check(reply(GOOD), CHUNKS).action
        == Action.FALLBACK
    )
    assert (
        GroundednessChecker(cfg, scorer=FakeScorer(1.0))
        .check(reply(f"{GOOD} {INVENTED}"), CHUNKS)
        .action
        == Action.ALLOW
    )


# ---------- list markers (docs/specs/fix-claim-splitting.md) ----------


@pytest.mark.parametrize(
    ("text", "want"),
    [
        (
            "1. Block your card in the SDB app or call 1660-01-12345.",
            ["Block your card in the SDB app or call 1660-01-12345."],
        ),
        (
            "Steps:\n1. Open the SDB app.\n2. Select Cards and Block.\n3) Call the hotline.",
            ["Steps:", "Open the SDB app.", "Select Cards and Block.", "Call the hotline."],
        ),
        (
            "- Keep your PIN safe.\n* Never share your OTP.",
            ["Keep your PIN safe.", "Never share your OTP."],
        ),
        ("The limit is 5. Ask a branch.", ["The limit is 5.", "Ask a branch."]),
        ("Pay Rs. 500 at the branch.", ["Pay Rs. 500 at the branch."]),
    ],
)
def test_list_markers_not_claims(text, want):
    assert split_claims(text) == want


def test_step_numbers_not_checked_as_facts(checker):
    chunks = {"card-blocking#2": "Block your card in the app. Then call the hotline."}
    reply = SupportReply(
        answer="1. Block your card in the app.\n2. Then call the hotline.",
        citations=["card-blocking#2"],
        intent="cards",
        confidence=0.9,
        escalate=False,
    )
    r = checker.check(reply, chunks)
    assert r.action == Action.ALLOW
    assert all(not c["numbers_missing"] for c in r.details["claims"])
