"""Local sentence-transformers embedding model wrapper.

Loads the model once and reuses it across encode calls (important for AWS, where
you load at startup and serve many requests). CPU-friendly, no API key, offline
after the weights are cached.

Model: paraphrase-multilingual-mpnet-base-v2 (768-dim) — stronger ranking quality
than MiniLM-L12 (384-dim) at ~3x the embed cost; events are embedded once, so the
per-request cost is unchanged. Swappable: pass any model name/path to the
constructor (the dim is read from the loaded model) and re-embed the index.
"""

from __future__ import annotations

import numpy as np

# NOTE: keep in sync with EMBEDDING_MODEL_NAME in src/recommender_api/Dockerfile.
# Changing the model invalidates every stored vector — the index must be re-embedded
# (index_store does this automatically: it hashes vectors with the model name).
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


class EmbeddingModel:
    """Thin wrapper around a sentence-transformers model.

    Usage:
        model = EmbeddingModel()                 # loads once
        vecs = model.encode(["text1", "text2"])  # (n, dim) float32, L2-normalized
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        # Imported lazily so importing this module doesn't pull torch until needed.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        kwargs: dict = {}
        if device:
            kwargs["device"] = device
        self._model = SentenceTransformer(model_name, **kwargs)
        # get_sentence_embedding_dimension() was renamed to get_embedding_dimension()
        # in newer sentence-transformers; use whichever is available.
        dim_fn = getattr(self._model, "get_embedding_dimension", None) or getattr(
            self._model, "get_sentence_embedding_dimension"
        )
        self.dim: int = int(dim_fn())

    def encode(self, texts: list[str], normalize: bool = True, prompt_name: str | None = None) -> np.ndarray:
        """Embed a list of strings -> (n, dim) float32 array.

        With normalize=True (default) rows are L2-normalized so that a dot product
equals cosine similarity.

        prompt_name: "query" for user-side text, "passage" for event text. Used only
        when the loaded model defines that prompt (e.g. E5 models require the
        "query: "/"passage: " prefixes); silently ignored otherwise (mpnet, MiniLM).
        """
        if isinstance(texts, str):
            texts = [texts]
        kwargs: dict = {}
        if prompt_name and prompt_name in (getattr(self._model, "prompts", None) or {}):
            kwargs["prompt_name"] = prompt_name
        vecs = self._model.encode(
            list(texts),
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
            **kwargs,
        )
        return np.asarray(vecs, dtype=np.float32)

    def __repr__(self) -> str:  # pragma: no cover
        return f"EmbeddingModel({self.model_name!r}, dim={self.dim})"
