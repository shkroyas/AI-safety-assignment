"""Labeled eval sets in data/eval/*.jsonl and the stratified dev/test split."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from guardbank.config import ROOT

EVAL_DIR = ROOT / "data" / "eval"
SETS = (
    "injection",
    "injection_pii",
    "crisis",
    "pii",
    "topics",
    "groundedness",
    "groundedness_live",
    "leakage",
    "leakage_pii",
    "chunk_poison",
)
MIN_SIZES = {
    "injection": 60,
    "injection_pii": 40,
    "crisis": 25,
    "pii": 45,
    "topics": 55,
    "groundedness": 45,
    "groundedness_live": 20,
    "leakage": 25,
    "leakage_pii": 25,
    "chunk_poison": 12,
}
DEV_SHARE = 0.3


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str


class TextItem(_Item):
    text: str
    label: int
    kind: str


class PiiItem(_Item):
    text: str
    labels: list[str] = Field(default_factory=list)
    kind: str


class TopicItem(_Item):
    text: str
    label: str


class GroundItem(_Item):
    claim: str
    evidence: list[str]
    label: int
    kind: str
    note: str = ""  # why the label (groundedness_live: hand-labelled against the evidence)


class LeakItem(_Item):
    answer: str
    label: int
    kind: str
    context: str = ""


MODELS: dict[str, type[_Item]] = {
    "injection": TextItem,
    "injection_pii": TextItem,
    "crisis": TextItem,
    "pii": PiiItem,
    "topics": TopicItem,
    "groundedness": GroundItem,
    "groundedness_live": GroundItem,
    "leakage": LeakItem,
    "leakage_pii": LeakItem,
    "chunk_poison": TextItem,
}


def load_set(name: str, root: Path = EVAL_DIR) -> list[Any]:
    model = MODELS[name]
    lines = (root / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [model.model_validate(json.loads(line)) for line in lines if line.strip()]


def item_text(name: str, item: Any) -> str:
    if name in ("groundedness", "groundedness_live"):
        return item.claim
    if name in ("leakage", "leakage_pii"):
        return item.answer
    return item.text


def label_of(name: str, item: Any) -> Any:
    if name == "pii":
        return int(bool(item.labels))
    return item.label


def split_ids(pairs: list[tuple[str, Any]], dev_share: float = DEV_SHARE) -> dict[str, str]:
    """Stratified by label; within a label, ids ordered by sha256 and the first share go to dev."""
    by_label: dict[Any, list[str]] = {}
    for item_id, label in pairs:
        by_label.setdefault(label, []).append(item_id)
    out: dict[str, str] = {}
    for group in by_label.values():
        group.sort(key=lambda i: hashlib.sha256(i.encode()).hexdigest())
        k = round(dev_share * len(group))
        if len(group) >= 2:
            k = min(max(k, 1), len(group) - 1)
        for n, item_id in enumerate(group):
            out[item_id] = "dev" if n < k else "test"
    return out


def split(name: str, items: list[Any]) -> dict[str, str]:
    return split_ids([(it.id, label_of(name, it)) for it in items])
