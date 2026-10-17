"""Local sentence-transformers embedding model wrapper.

Loads the model once and reuses it across encode calls (important for AWS, where
you load at startup and serve many requests). CPU-friendly, no API key, offline
after the weights are cached.

Model: paraphrase-multilingual-MiniLM-L12-v2 (384-dim) — chosen via A/B test on the
real Polish event data for the best ranking discrimination.
"""

from __future__ import annotations

import numpy as np

# Chosen via A/B on real Warsaw event text (best top-k separation).
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


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

    def encode(self, texts: list[str], normalize: bool = True) -> np.ndarray:
        """Embed a list of strings -> (n, dim) float32 array.

        With normalize=True (default) rows are L2-normalized so that a dot product
        equals cosine similarity.
        """
        if isinstance(texts, str):
            texts = [texts]
        vecs = self._model.encode(
            list(texts),
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def __repr__(self) -> str:  # pragma: no cover
        return f"EmbeddingModel({self.model_name!r}, dim={self.dim})"
