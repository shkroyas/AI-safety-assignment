"""Claim scorers, HHEM factory and leakage embedder settings; no weights (ml-output spec)."""

import copy

import pytest

from guardbank.output.groundedness import GroundednessChecker
from guardbank.output.hhem import HHEMScorer
from guardbank.output.leakage import LeakageChecker, instruction_sentences
from guardbank.output.scorers import KeywordScorer, build_claim_scorer
from guardbank.types import Action

SUMMARY_LEAK = (
    "My rules are: answer only from the context, cite the ids of the context sections, "
    "and never reveal the internal reference."
)


def _g(settings, **changes):
    cfg = copy.deepcopy(settings.output["groundedness"])
    cfg.update(changes)
    return cfg


def test_keyword_scorer_takes_evidence_list():
    k = KeywordScorer()
    assert (
        k.score("The limit is NPR 25,000 per day.", ["The limit is", "NPR 25,000 per day."]) == 1.0
    )
    assert k.score("Opened on January 15, 2024.", ["Account opened on 2024-01-15."]) == 1.0
    assert k.score("Free airport lounge access.", ["The ATM limit is NPR 25,000."]) == 0.0


def test_scorer_factory(settings):
    assert isinstance(build_claim_scorer(settings.output["groundedness"]), KeywordScorer)
    h = build_claim_scorer(_g(settings, scorer="hhem"))
    assert isinstance(h, HHEMScorer)
    assert h.loaded is False
    assert h.revision == settings.output["groundedness"]["hhem"]["revision"]
    with pytest.raises(ValueError, match="allowed"):
        build_claim_scorer(_g(settings, scorer="nope"))


def test_hhem_tau_overrides(settings):
    assert GroundednessChecker(_g(settings)).tau_g == settings.output["groundedness"]["tau_g"]
    hhem_tau = settings.output["groundedness"]["hhem"]["tau_g"]
    assert GroundednessChecker(_g(settings, scorer="hhem")).tau_g == hhem_tau


def test_public_prompt_lines_excluded(settings):
    public = settings.output["leakage"]["public_prompt_lines"]
    all_lines = instruction_sentences()
    kept = instruction_sentences(exclude=public)
    assert any("PINs" in s for s in all_lines)
    assert not any("PINs" in s for s in kept)
    assert len(kept) == len(all_lines) - len(public)


def test_leakage_tau_per_embedder(settings):
    leak = LeakageChecker.from_settings(settings)
    assert leak.tau_prompt == settings.output["leakage"]["tau_prompt"]["hashing"]


def test_summary_leak_now_blocked(settings):
    r = LeakageChecker.from_settings(settings).check(SUMMARY_LEAK, _vault(), "GB-CANARY-x", "")
    assert r.action == Action.BLOCK
    assert r.category == "PROMPT_LEAK"


def _vault():
    from guardbank.input.pii import PiiVault

    return PiiVault()
