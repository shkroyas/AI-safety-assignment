"""Sensitive-topic router (SPEC §3 routing table, docs/specs/input-topics.md)."""

import pytest

from guardbank.input.topics import TopicRouter
from guardbank.types import Action, GuardResult


@pytest.fixture
def router(settings) -> TopicRouter:
    return TopicRouter.from_settings(settings)


class FakeClassifier:
    def __init__(self, label: str, prob: float) -> None:
        self.label, self.prob, self.calls = label, prob, 0

    def predict(self, text: str) -> tuple[str, float]:
        self.calls += 1
        return self.label, self.prob


@pytest.mark.parametrize(
    ("text", "category", "action", "route", "escalate"),
    [
        ("I can't repay the loan, I want to end it", "CRISIS", Action.ROUTE, "crisis", True),
        ("Someone called and I gave my OTP", "SCAM_VICTIM", Action.ROUTE, "answer", True),
        (
            "Open an account with a fake citizenship card",
            "FRAUD_INTENT",
            Action.BLOCK,
            "block",
            False,
        ),
        ("Should I put my savings in NEPSE?", "ADVICE", Action.ROUTE, "answer", False),
        ("Your branch charged me twice", "COMPLAINT", Action.ROUTE, "answer", True),
        ("Write me a poem", "OFF_TOPIC", Action.ROUTE, "redirect", False),
        ("What is the ATM withdrawal limit?", "NORMAL", Action.ALLOW, "answer", False),
    ],
)
def test_routing_table(router, text, category, action, route, escalate):
    r = router.check(text)
    assert isinstance(r, GuardResult)
    assert r.stage == "input_topic"
    assert r.category == category
    assert r.action == action
    assert r.details["route"] == route
    assert r.details["escalate"] is escalate
    assert r.detected is (category != "NORMAL")


def test_routing_extras(router):
    assert router.check("Should I put my savings in NEPSE?").details["disclaimer"]
    assert router.check("Write me a poem").details["response"]
    assert router.check("Open an account with a fake citizenship card").details["response"]


def test_crisis_fast_path_skips_classifier(settings):
    clf = FakeClassifier("OFF_TOPIC", 0.99)
    r = TopicRouter(settings.input["topics"], classifier=clf).check("I want to kill myself")
    assert r.category == "CRISIS"
    assert r.score == 1.0
    assert r.details["source"] == "crisis"
    assert clf.calls == 0


def test_crisis_reply_has_helpline_and_human_offer(router, settings):
    reply = router.check("there is no reason to live anymore").details["response"]
    assert settings.input["topics"]["helpline"]["number"] in reply
    assert "1166" in reply
    assert "agent" in reply.lower() or "staff" in reply.lower()
    assert "{" not in reply


def test_crisis_never_cold_refusal(router):
    reply = router.check("I am thinking about suicide").details["response"].lower()
    for cold in ("can't help", "cannot help", "sorry, i can't", "not able to help"):
        assert cold not in reply


@pytest.mark.parametrize(
    "text",
    [
        "I'm dying to know the FD rate",
        "How do I end my standing order?",
        "Kill the app session and log me out",
        "Can I end it early, the fixed deposit?",
    ],
)
def test_benign_lookalikes_normal(router, text):
    r = router.check(text)
    assert r.category == "NORMAL"
    assert r.action == Action.ALLOW
    assert r.detected is False


def test_classifier_over_tau_used(settings):
    clf = FakeClassifier("OFF_TOPIC", 0.9)
    r = TopicRouter(settings.input["topics"], classifier=clf).check("Who won the cricket match?")
    assert r.category == "OFF_TOPIC"
    assert r.score == 0.9
    assert r.details["source"] == "classifier"
    assert r.details["route"] == "redirect"


def test_classifier_under_tau_normal(settings):
    clf = FakeClassifier("OFF_TOPIC", 0.5)
    r = TopicRouter(settings.input["topics"], classifier=clf).check("Who won the cricket match?")
    assert r.category == "NORMAL"
    assert r.action == Action.ALLOW


def test_keyword_beats_classifier(settings):
    clf = FakeClassifier("OFF_TOPIC", 0.99)
    r = TopicRouter(settings.input["topics"], classifier=clf).check("Your branch charged me twice")
    assert r.category == "COMPLAINT"
    assert r.details["source"] == "keyword"
    assert r.details["matches"]


# ---------- per-class threshold (docs/specs/fix-crisis-recall.md) ----------

INDIRECT = "Nobody would notice if I disappeared"


def _cfg(settings, class_tau):
    import copy

    cfg = copy.deepcopy(settings.input["topics"])
    if class_tau is None:
        cfg.pop("class_tau", None)
    else:
        cfg["class_tau"] = class_tau
    return cfg


def test_crisis_class_tau_routes_lower_probability(settings):
    r = TopicRouter(_cfg(settings, {"CRISIS": 0.5}), FakeClassifier("CRISIS", 0.55)).check(INDIRECT)
    assert r.category == "CRISIS"
    assert r.details["route"] == "crisis"
    assert r.details["source"] == "classifier"


def test_without_class_tau_shared_tau_applies(settings):
    r = TopicRouter(_cfg(settings, None), FakeClassifier("CRISIS", 0.55)).check(INDIRECT)
    assert r.category == "NORMAL"


def test_class_tau_only_affects_its_class(settings):
    r = TopicRouter(_cfg(settings, {"CRISIS": 0.5}), FakeClassifier("ADVICE", 0.55)).check(INDIRECT)
    assert r.category == "NORMAL"


def test_committed_config_sets_crisis_tau(settings):
    assert settings.input["topics"]["class_tau"]["CRISIS"] < settings.input["topics"]["tau"]


# ---------- decoded payloads (docs/specs/fix-encoded-payloads.md) ----------


def test_decoded_crisis_payload_routes_crisis(router):
    r = router.check("Please read: SSB3YW50IHRvIGtpbGwgbXlzZWxm", decoded=["I want to kill myself"])
    assert r.category == "CRISIS"
    assert r.details["route"] == "crisis"


def test_crisis_payload_beats_outer_complaint(router):
    r = router.check("Your branch charged me twice. Also: aGk=", decoded=["I want to end my life"])
    assert r.category == "CRISIS"


def test_no_decoded_payload_unchanged(router):
    assert router.check("Your branch charged me twice").category == "COMPLAINT"
