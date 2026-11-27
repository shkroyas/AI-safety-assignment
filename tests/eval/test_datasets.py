"""Labeled eval sets (docs/specs/eval.md). Asserts structure only; never prints whole sets."""

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from guardbank.evaluation.datasets import MIN_SIZES, SETS, item_text, label_of, load_set, split

ROOT = Path(__file__).resolve().parents[2]


def _norm(t: str) -> str:
    return " ".join(t.lower().split())


@pytest.fixture(scope="module")
def sets():
    return {name: load_set(name) for name in SETS}


def test_sizes_and_unique_ids(sets):
    all_ids = []
    for name, items in sets.items():
        assert len(items) >= MIN_SIZES[name], name
        all_ids += [it.id for it in items]
    assert len(all_ids) == len(set(all_ids))
    assert sum(len(v) for v in sets.values()) >= 250


@pytest.mark.parametrize("name", SETS)
def test_split_stratified(sets, name):
    items = sets[name]
    if name == "chunk_poison":
        assert {label_of(name, it) for it in items} == {1}
    sp = split(name, items)
    assert set(sp) == {it.id for it in items}
    by_label: dict = {}
    for it in items:
        by_label.setdefault(label_of(name, it), []).append(sp[it.id])
    for label, parts in by_label.items():
        c = Counter(parts)
        assert c["dev"] >= 1 and c["test"] >= 1, (name, label)
        assert abs(c["dev"] / len(parts) - 0.3) <= 0.05 + 1 / len(parts), (name, label)
    assert split(name, items) == sp  # deterministic


def test_binary_sets_have_both_labels(sets):
    for name in ("injection", "injection_pii", "crisis", "pii", "groundedness", "leakage"):
        assert {label_of(name, it) for it in sets[name]} == {0, 1}, name


def test_topics_cover_all_categories(sets, settings):
    assert {it.label for it in sets["topics"]} == set(settings.input["topics"]["routes"])


def test_no_overlap_with_cases_or_training(sets):
    cases = yaml.safe_load((ROOT / "tests" / "cases.yaml").read_text(encoding="utf-8"))
    train = yaml.safe_load((ROOT / "data" / "topics" / "train.yaml").read_text(encoding="utf-8"))
    taken = {_norm(c["input"]) for c in cases} | {_norm(t) for v in train.values() for t in v}
    for name, items in sets.items():
        clash = [it.id for it in items if _norm(item_text(name, it)) in taken]
        assert clash == [], name


def _luhn(d: str) -> bool:
    s = 0
    for i, ch in enumerate(reversed(d)):
        x = int(ch) * (2 if i % 2 else 1)
        s += x - 9 if x > 9 else x
    return s % 10 == 0


def test_only_test_card_numbers(sets):
    for name, items in sets.items():
        for it in items:
            for m in re.finditer(r"\d(?:[ -]?\d){12,18}", item_text(name, it)):
                digits = re.sub(r"\D", "", m.group(0))
                if _luhn(digits):
                    assert digits.startswith("4111"), it.id


def test_injection_pii_items_contain_pii(sets, settings):
    """Every injection_pii item has PII the stub redactor finds (else it tests nothing)."""
    from guardbank.input.normalizer import Normalizer
    from guardbank.input.pii import PiiRedactor, PiiVault

    norm, red = Normalizer.from_settings(settings), PiiRedactor.from_settings(settings)
    missing = []
    for it in sets["injection_pii"]:
        n = norm.check(it.text).details
        if not red.check(n["normalized"], PiiVault(), decoded=n["decoded"]).detected:
            missing.append(it.id)
    assert missing == []
    kinds = {it.label: set() for it in sets["injection_pii"]}
    for it in sets["injection_pii"]:
        kinds[it.label].add(it.kind)
    assert len(kinds[0]) >= 5 and len(kinds[1]) >= 3
