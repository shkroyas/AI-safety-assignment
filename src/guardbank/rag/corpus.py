"""Load the Markdown policy corpus and split it into section chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    topic: str
    body: str
    poisoned: bool = False


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    title: str
    text: str
    poisoned: bool = False


def load_doc(path: Path) -> Doc:
    match = _FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path}: missing YAML front matter")
    meta = yaml.safe_load(match.group(1))
    return Doc(
        id=meta["id"],
        title=meta["title"],
        topic=meta["topic"],
        body=match.group(2).strip(),
        poisoned=bool(meta.get("poisoned", False)),
    )


def load_corpus(directory: str | Path) -> list[Doc]:
    return [load_doc(p) for p in sorted(Path(directory).glob("*.md"))]


def chunk_docs(docs: list[Doc]) -> list[Chunk]:
    """One chunk per `##` section; the doc's intro (before the first `##`) is chunk 0."""
    chunks: list[Chunk] = []
    for doc in docs:
        parts = re.split(r"\n(?=## )", doc.body)
        for n, part in enumerate(p.strip() for p in parts):
            if not part:
                continue
            chunks.append(
                Chunk(
                    id=f"{doc.id}#{n}",
                    doc_id=doc.id,
                    title=doc.title,
                    text=part,
                    poisoned=doc.poisoned,
                )
            )
    return chunks
