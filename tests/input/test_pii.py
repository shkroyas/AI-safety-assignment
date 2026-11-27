"""Input PII redaction (SPEC §3 PII row, docs/specs/input-pii.md). All values are synthetic."""

import base64
import copy

import pytest

from guardbank.input.pii import PiiRedactor, PiiVault
from guardbank.types import Action, GuardResult

TEST_CARD = "4111111111111111"  # standard Luhn-valid test number


@pytest.fixture
def pii(settings) -> PiiRedactor:
    return PiiRedactor.from_settings(settings)


@pytest.fixture
def vault() -> PiiVault:
    return PiiVault()


@pytest.mark.parametrize(
    ("text", "value", "label"),
    [
        ("My citizenship no is 12-01-75-01234.", "12-01-75-01234", "NP_CITIZENSHIP"),
        ("My PAN is 301234567 for the form.", "301234567", "NP_PAN"),
        ("Call me on +977-9812345678 please.", "+977-9812345678", "NP_PHONE"),
        ("Call me on 9801234567 please.", "9801234567", "NP_PHONE"),
        ("My account number is 0123456789012 at Lalitpur.", "0123456789012", "ACCOUNT_NO"),
        (f"Card {TEST_CARD} was charged twice.", TEST_CARD, "CARD"),
        ("The OTP is 482913, is that fine?", "482913", "OTP"),
        ("my password is Hunter2! now", "Hunter2!", "PASSWORD"),
        ("Mail me at sita.test@example.com today.", "sita.test@example.com", "EMAIL"),
    ],
)
def test_each_nepal_format_redacted(pii, vault, text, value, label):
    r = pii.check(text, vault)
    assert value not in r.details["redacted"]
    assert f"<{label}_1>" in r.details["redacted"]
    assert [s.label for s in r.spans] == [label]
    span = r.spans[0]
    assert text[span.start : span.end] == value


def test_pan_needs_context(pii, vault):
    r = pii.check("Reference 301234567 is on the slip.", vault)
    assert r.detected is False


def test_order_id_not_account(pii, vault):
    text = "Where is order #1234567890123?"
    r = pii.check(text, vault)
    assert r.detected is False
    assert r.details["redacted"] == text


def test_card_luhn_only(pii, vault):
    assert pii.check("Card 4111111111111112 was declined.", vault).detected is False
    assert pii.check("Card 4111 1111 1111 1111 was declined.", vault).spans[0].label == "CARD"


def test_never_share_warning(pii, settings, vault):
    r = pii.check(f"my card is {TEST_CARD}", vault)
    assert r.details["warning"] == settings.input["pii"]["warning"]
    assert pii.check("Mail me at sita.test@example.com", vault).details["warning"] is None


def test_same_value_same_token(pii, vault):
    r = pii.check("Call 9812345678, or 9812345678 again, or 9801111111.", vault)
    assert r.details["redacted"] == "Call <NP_PHONE_1>, or <NP_PHONE_1> again, or <NP_PHONE_2>."
    r2 = pii.check("Still 9812345678.", vault)  # same session vault, later turn
    assert r2.details["redacted"] == "Still <NP_PHONE_1>."


def test_vault_restore(pii, vault):
    text = "Call +977-9812345678 or mail sita.test@example.com"
    r = pii.check(text, vault)
    assert vault.restore(r.details["redacted"]) == text
    assert vault.restore("no tokens <UNKNOWN_9>") == "no tokens <UNKNOWN_9>"


def test_spans_hold_token_not_value(pii, vault):
    r = pii.check(f"card {TEST_CARD}", vault)
    assert r.spans[0].text == "<CARD_1>"
    assert TEST_CARD not in r.model_dump_json()


def test_decoded_payload_scanned(pii, vault):
    payload = "my otp is 482913"
    b64 = base64.b64encode(payload.encode()).decode()
    r = pii.check(f"decode {b64}", vault, decoded=[payload])
    assert r.detected is True
    assert r.details["decoded_redacted"] == ["my otp is <OTP_1>"]
    assert r.details["warning"] is not None
    assert r.category == "OTP"


def test_clean_text_allow(pii, vault):
    text = "What is the ATM withdrawal limit per day?"
    r = pii.check(text, vault)
    assert isinstance(r, GuardResult)
    assert r.stage == "input_pii"
    assert (r.detected, r.score, r.action, r.category) == (False, 0.0, Action.ALLOW, None)
    assert r.details["redacted"] == text


def test_detected_result_fields(pii, vault):
    r = pii.check("Call 9812345678", vault)
    assert (r.detected, r.score, r.action, r.category) == (True, 1.0, Action.REDACT, "NP_PHONE")


def test_config_drives_labels(settings, vault):
    cfg = copy.deepcopy(settings.input["pii"])
    cfg["labels"] = [x for x in cfg["labels"] if x != "EMAIL"]
    cfg["context_words"]["NP_PAN"] = ["tax id"]
    p = PiiRedactor(cfg)
    assert p.check("mail sita.test@example.com", vault).detected is False
    assert p.check("my PAN is 301234567", vault).detected is False
    assert p.check("my tax id is 301234567", vault).spans[0].label == "NP_PAN"


def test_overlap_longest_wins(pii, vault):
    r = pii.check("account +977-9812345678", vault)
    assert [s.label for s in r.spans] == ["NP_PHONE"]


@pytest.mark.slow
def test_presidio_person_redacted(settings, vault):
    pytest.importorskip("presidio_analyzer")
    cfg = copy.deepcopy(settings.input["pii"])
    cfg["backend"] = "presidio"
    r = PiiRedactor(cfg).check("Hello, my name is Ram Bahadur Thapa and I live in Pokhara.", vault)
    labels = {s.label for s in r.spans}
    assert "PERSON" in labels
    assert "Ram Bahadur Thapa" not in r.details["redacted"]


# ---------- Nepali landlines (docs/specs/fix-landline-pii.md) ----------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Phone me at home on 01-5970123 after six.", "01-5970123"),
        ("Our landline is 01 4412345.", "01 4412345"),
        ("The Pokhara office number is 061-523456.", "061-523456"),
        ("From abroad dial +977-1-5970123.", "+977-1-5970123"),
        ("My shop line is +977 21 456789.", "+977 21 456789"),
    ],
)
def test_landline_found_as_phone(pii, vault, text, value):
    r = pii.check(text, vault)
    assert [s.label for s in r.spans] == ["NP_PHONE"]
    span = r.spans[0]
    assert text[span.start : span.end] == value


@pytest.mark.parametrize(
    "text",
    [
        "The statement date is 2024-01-15.",
        "I paid NPR 1,50,000 last week.",
        "My order ORD-015970123 has not arrived.",
        "Call the hotline on 1660-01-12345 to block it.",
        "Ref 0123456789 is the old file number.",
    ],
)
def test_landline_lookalikes_not_phone(pii, text):
    assert "NP_PHONE" not in [label for _, _, label in pii.find(text)]


# ---------- Devanagari digits (docs/specs/fix-devanagari-digits.md) ----------


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Call me on ९८४१२३४५६७ please.", "NP_PHONE"),
        ("My account number is ०१२३४५६७८९०१२.", "ACCOUNT_NO"),
        ("My citizenship no is १२-०१-७५-०१२३४.", "NP_CITIZENSHIP"),
        ("The OTP is ४८२९१३, is that fine?", "OTP"),
        ("Card ४१११ ११११ ११११ ११११ was charged twice.", "CARD"),
    ],
)
def test_devanagari_numbers_found_after_normalizing(settings, pii, vault, text, label):
    from guardbank.input.normalizer import Normalizer

    normalized = Normalizer.from_settings(settings).check(text).details["normalized"]
    assert [lab for _, _, lab in pii.find(normalized)] == [label]
