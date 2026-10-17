"""Opt-in tests against the real sentence-transformers model.

Skipped unless RUN_MODEL_TESTS=1 (they download/load ~470 MB of weights):

    RUN_MODEL_TESTS=1 .venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MODEL_TESTS") != "1",
    reason="set RUN_MODEL_TESTS=1 to load the real embedding model",
)


@pytest.fixture(scope="module")
def model():
    from recommender import EmbeddingModel

    return EmbeddingModel()


def test_dim_matches_default_model(model):
    from recommender import DEFAULT_MODEL

    assert DEFAULT_MODEL.endswith("mpnet-base-v2")
    assert model.dim == 768


def test_encode_is_normalized_and_consistent(model):
    import numpy as np

    vecs = model.encode(["Koncert jazzowy", "Koncert jazzowy"])
    assert vecs.shape == (2, model.dim)
    assert vecs.dtype.name == "float32"
    assert abs(float((vecs[0] ** 2).sum()) - 1.0) < 1e-4
    # Same text in one batch: equal up to float32 matmul noise (~1e-7).
    assert np.allclose(vecs[0], vecs[1], atol=1e-6)
    # Deterministic across calls.
    assert np.allclose(model.encode(["Koncert jazzowy"])[0], vecs[0], atol=1e-6)


def test_related_text_scores_higher_than_unrelated(model):
    import numpy as np

    q = model.encode(["koncert muzyki na żywo"], prompt_name="query")[0]
    good = model.encode(["Wieczór improwizacji jazzowej w klubie"], prompt_name="passage")[0]
    bad = model.encode(["Warsztaty robotyki dla dzieci z klocków"], prompt_name="passage")[0]
    assert float(np.dot(q, good)) > float(np.dot(q, bad))


def test_prompt_name_is_ignored_by_models_without_prompts(model):
    """mpnet defines no prompts, so prompt_name must not change the vector."""
    import numpy as np

    a = model.encode(["ten sam tekst"])[0]
    b = model.encode(["ten sam tekst"], prompt_name="passage")[0]
    assert np.allclose(a, b)


def test_end_to_end_ranking_with_real_model():
    from recommender import Recommender

    events = [
        {"id": "jazz", "title": "Koncert jazzowy",
         "lead": "Wieczór improwizacji jazzowej.", "category": [{"name": "Muzyka"}],
         "district": [{"name": "Śródmieście"}],
         "occurrences": [{"start": "2026-10-20T20:00:00", "end": "2026-10-20T22:00:00"}]},
        {"id": "kids", "title": "Warsztaty robotyki dla dzieci",
         "lead": "Roboty z klocków LEGO.", "category": [{"name": "Edukacja"}],
         "district": [{"name": "Praga"}],
         "occurrences": [{"start": "2026-10-21T11:00:00", "end": "2026-10-21T13:00:00"}]},
    ]
    rec = Recommender(events, api_key=None)
    out = rec.recommend({"query": "koncert muzyki na żywo"}, top_k=2, explain=False)
    assert out[0].event_id == "jazz"
