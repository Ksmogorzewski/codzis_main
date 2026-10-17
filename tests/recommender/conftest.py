"""Shared fixtures: run the pipeline without torch / a downloaded model.

`FakeEmbeddingModel` implements the same surface the pipeline uses as
`EmbeddingModel` (`.dim` and `.encode(texts, normalize=..., prompt_name=...)`) but
maps text to a deterministic bag-of-words vector. That keeps retrieval/ranking tests
fast, offline and CPU-free while still exercising the real code paths (chunking,
indexing, filtering, boosts, dedupe, diversification).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_TOKEN_RE = re.compile(r"[a-z0-9ąćęłńóśźż]+")


class FakeEmbeddingModel:
    """Deterministic hashing embedder: same API as EmbeddingModel, no torch."""

    def __init__(self, dim: int = 64):
        self.dim = dim
        self.prompt_calls: list[str | None] = []

    def _tokens(self, text: str) -> list[str]:
        return _TOKEN_RE.findall((text or "").lower())

    def encode(self, texts, normalize: bool = True, prompt_name: str | None = None):
        self.prompt_calls.append(prompt_name)
        if isinstance(texts, str):
            texts = [texts]
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok in self._tokens(text):
                h = int(hashlib.sha1(tok.encode()).hexdigest()[:8], 16)
                out[row, h % self.dim] += 1.0
        if normalize:
            norms = np.linalg.norm(out, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            out = out / norms
        return out.astype(np.float32)


@pytest.fixture
def fake_model() -> FakeEmbeddingModel:
    return FakeEmbeddingModel()


def make_event(eid, title, *, lead="", district="Śródmieście", start="2026-10-20T18:00:00",
               end="2026-10-20T20:00:00", **extra):
    """Minimal schema-v1 event record."""
    event = {
        "id": eid,
        "title": title,
        "lead": lead,
        "category": [{"name": "Kultura"}],
        "district": [{"name": district}],
        "occurrences": [{"start": start, "end": end}],
    }
    event.update(extra)
    return event


@pytest.fixture
def events():
    return [
        make_event("jazz", "Koncert jazzowy", lead="Wieczór improwizacji jazzowej. Wstęp wolny.",
                   tags={"theme": ["Jazz", "Muzyka na żywo"], "format": ["Koncert"],
                         "cost": "Bezpłatne"}),
        make_event("rock", "Koncert rockowy", lead="Głośny koncert zespołu rockowego.",
                   district="Praga-Południe",
                   tags={"theme": ["Rock"], "format": ["Koncert"], "cost": "Płatne"}),
        make_event("kids", "Warsztaty robotyki dla dzieci", lead="Roboty z klocków LEGO.",
                   start="2026-10-21T11:00:00", end="2026-10-21T13:00:00",
                   tags={"theme": ["Nauka"], "format": ["Warsztaty"],
                         "audience": ["Dzieci (7-12)"]}),
        make_event("pool1", "Zajęcia pływania - grupa 1", lead="Basen, poziom podstawowy.",
                   start="2026-10-22T17:00:00", end="2026-10-22T18:00:00",
                   tags={"theme": ["Sport"], "format": ["Zajęcia"]}),
        make_event("pool2", "Zajęcia pływania - grupa 2", lead="Basen, poziom podstawowy.",
                   start="2026-10-23T17:00:00", end="2026-10-23T18:00:00",
                   tags={"theme": ["Sport"], "format": ["Zajęcia"]}),
    ]
