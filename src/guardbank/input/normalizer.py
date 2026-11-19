"""Input normalizer (SPEC §2 step 1, docs/specs/input-normalizer.md).

Canonicalises user text so later detectors see one form: NFKC, zero-width/bidi stripping,
homoglyph mapping, whitespace collapse. Decodes obvious base64/hex tokens once so their
payload is scanned too. Never blocks.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
import unicodedata
from typing import Any

from guardbank.types import Action, GuardResult, Span

STAGE = "normalizer"
_CHANGE_ORDER = ("nfkc", "zero_width", "homoglyph", "base64", "hex")
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")
_TOKEN = re.compile(r"(?<![A-Za-z0-9+/=])(?:0x)?[A-Za-z0-9+/]+={0,2}(?![A-Za-z0-9+/=])")
_HEX = re.compile(r"[0-9A-Fa-f]+")


class Normalizer:
    def __init__(self, config: dict[str, Any]) -> None:
        decode = config["decode"]
        self.min_len: int = decode["min_len"]
        self.min_printable: float = decode["min_printable"]
        self.homoglyphs: dict[str, str] = dict(config.get("homoglyphs", {}))
        self._table = str.maketrans(self.homoglyphs)

    @classmethod
    def from_settings(cls, settings: Any) -> Normalizer:
        return cls(settings.input["normalizer"])

    def check(self, text: str) -> GuardResult:
        t0 = time.perf_counter()
        spans = self._char_spans(text)

        normalized = unicodedata.normalize("NFKC", text)
        normalized = _INVISIBLE.sub("", normalized)
        normalized = normalized.translate(self._table)
        normalized = " ".join(normalized.split())

        decoded, decode_spans = self._decode(normalized, text)
        spans += decode_spans

        found = {s.label for s in spans}
        changes = [c for c in _CHANGE_ORDER if c in found]
        if found & {"homoglyph", "base64", "hex"}:
            score = 1.0
        elif changes:
            score = 0.5
        else:
            score = 0.0
        return GuardResult(
            stage=STAGE,
            detected=bool(changes),
            score=score,
            spans=sorted(spans, key=lambda s: s.start),
            action=Action.ALLOW,
            latency_ms=(time.perf_counter() - t0) * 1000,
            details={"normalized": normalized, "decoded": decoded, "changes": changes},
        )

    def _char_spans(self, text: str) -> list[Span]:
        spans = []
        for i, ch in enumerate(text):
            if _INVISIBLE.fullmatch(ch):
                label = "zero_width"
            elif unicodedata.normalize("NFKC", ch) != ch:
                label = "nfkc"
            elif ch in self.homoglyphs:
                label = "homoglyph"
            else:
                continue
            spans.append(Span(start=i, end=i + 1, label=label, text=ch))
        return spans

    def _decode(self, normalized: str, original: str) -> tuple[list[str], list[Span]]:
        decoded: list[str] = []
        spans: list[Span] = []
        cursor = 0
        for m in _TOKEN.finditer(normalized):
            token = m.group()
            body = token[2:] if token.startswith("0x") else token
            if len(body) < self.min_len:
                continue
            result = self._try_hex(body)
            label = "hex"
            if result is None:
                result = self._try_base64(body)
                label = "base64"
            if result is None:
                continue
            decoded.append(result)
            start = original.find(token, cursor)
            if start >= 0:
                cursor = start + len(token)
                spans.append(Span(start=start, end=cursor, label=label, text=token))
        return decoded, spans

    def _try_hex(self, body: str) -> str | None:
        if len(body) % 2 or not _HEX.fullmatch(body):
            return None
        return self._printable(bytes.fromhex(body))

    def _try_base64(self, body: str) -> str | None:
        if len(body) % 4:
            return None
        try:
            raw = base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError):
            return None
        return self._printable(raw)

    def _printable(self, raw: bytes) -> str | None:
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if not s:
            return None
        ok = sum(c.isprintable() or c in "\t\n\r" for c in s)
        return s if ok / len(s) >= self.min_printable else None
