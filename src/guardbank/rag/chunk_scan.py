"""Injection scan on retrieved chunks (SPEC §2 step 5, docs/specs/chunk-scan.md).

Each chunk is normalized, then scanned with the input injection bank plus chunk-only
patterns. Poisoned chunks are dropped silently; the result records what was dropped.
"""

from __future__ import annotations

import copy
import re
import time
from typing import Any

from guardbank.input.detectors import ScoreDetector
from guardbank.input.injection import InjectionDetector
from guardbank.input.normalizer import Normalizer
from guardbank.rag.retriever import Hit
from guardbank.types import Action, GuardResult

STAGE = "chunk_scan"


class ChunkScanner:
    def __init__(
        self,
        config: dict[str, Any],
        injection_config: dict[str, Any],
        normalizer: Normalizer,
        classifier: ScoreDetector | None = None,
    ) -> None:
        allowed = "|".join(re.escape(d) for d in config["allowed_domains"])
        cfg = copy.deepcopy(injection_config)
        cfg["tau"] = config["tau"]
        for name, p in config["extra_patterns"].items():
            cfg["patterns"][name] = {
                "regex": p["regex"].replace("{allowed}", allowed),
                "weight": p["weight"],
            }
        self.detector = InjectionDetector(cfg, classifier=classifier)
        self.normalizer = normalizer

    @classmethod
    def from_settings(cls, settings: Any, classifier: ScoreDetector | None = None) -> ChunkScanner:
        return cls(
            settings.rag["chunk_scan"],
            settings.input["injection"],
            Normalizer.from_settings(settings),
            classifier=classifier,
        )

    def filter(self, hits: list[Hit]) -> tuple[list[Hit], GuardResult]:
        t0 = time.perf_counter()
        kept: list[Hit] = []
        dropped: list[dict[str, Any]] = []
        top: tuple[float, str | None] = (0.0, None)
        max_score = 0.0
        for hit in hits:
            norm = self.normalizer.check(hit.chunk.text).details
            r = self.detector.check(norm["normalized"], decoded=norm["decoded"])
            max_score = max(max_score, r.score)
            if not r.detected:
                kept.append(hit)
                continue
            dropped.append(
                {
                    "chunk_id": hit.chunk.id,
                    "doc_id": hit.chunk.doc_id,
                    "matches": r.details["matches"],
                    "score": r.score,
                }
            )
            if r.score > top[0]:
                top = (r.score, r.category)
        return kept, GuardResult(
            stage=STAGE,
            detected=bool(dropped),
            score=max_score,
            category=top[1],
            action=Action.DROP_CHUNK if dropped else Action.ALLOW,
            latency_ms=(time.perf_counter() - t0) * 1000,
            details={"dropped": dropped, "kept": [h.chunk.id for h in kept]},
        )
