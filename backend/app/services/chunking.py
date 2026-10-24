"""Structure-aware text chunking.

Strategy (deliberately simple and dependency-free so it is easy to reason about):

1. Normalise whitespace and split the document into paragraphs (blank-line separated).
2. Paragraphs that fit are kept whole; longer ones are split into sentences, and any
   sentence that is still too long is hard-wrapped on word boundaries.
3. These units are greedily packed into chunks of at most `chunk_size` characters.
4. Each new chunk starts with the trailing units of the previous chunk (up to
   `overlap` characters), so a fact that straddles a boundary is retrievable from both.

Paragraph boundaries are preferred split points because support articles (policies,
FAQs, troubleshooting steps) are usually written one idea per paragraph.
"""

import re
from dataclasses import dataclass

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class _Unit:
    text: str
    starts_paragraph: bool


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    units = list(_split_units(normalize_text(text), chunk_size))
    chunks: list[str] = []
    current: list[_Unit] = []

    for unit in units:
        if current and len(_join([*current, unit])) > chunk_size:
            chunks.append(_join(current))
            current = _overlap_tail(current, overlap)
            if len(_join([*current, unit])) > chunk_size:
                current = []
        current.append(unit)

    if current:
        chunks.append(_join(current))
    return chunks


def _split_units(text: str, chunk_size: int):
    for paragraph in _PARAGRAPH_BOUNDARY.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= chunk_size:
            yield _Unit(paragraph, starts_paragraph=True)
            continue
        pieces = [
            piece
            for sentence in _SENTENCE_BOUNDARY.split(paragraph)
            for piece in (_hard_wrap(sentence, chunk_size) if len(sentence) > chunk_size else [sentence])
        ]
        for index, piece in enumerate(pieces):
            yield _Unit(piece, starts_paragraph=index == 0)


def _hard_wrap(sentence: str, chunk_size: int) -> list[str]:
    """Split an over-long sentence on word boundaries (or mid-word as a last resort)."""
    pieces: list[str] = []
    current = ""
    for word in sentence.split():
        while len(word) > chunk_size:  # e.g. a long URL or base64 blob
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:chunk_size])
            word = word[chunk_size:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) > chunk_size:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(units: list[_Unit], overlap: int) -> list[_Unit]:
    """Trailing units of the previous chunk whose combined length fits in `overlap`."""
    tail: list[_Unit] = []
    for unit in reversed(units):
        if len(_join([unit, *tail])) > overlap:
            break
        tail.insert(0, unit)
    return tail


def _join(units: list[_Unit]) -> str:
    parts: list[str] = []
    for index, unit in enumerate(units):
        if index:
            parts.append("\n\n" if unit.starts_paragraph else " ")
        parts.append(unit.text)
    return "".join(parts)
