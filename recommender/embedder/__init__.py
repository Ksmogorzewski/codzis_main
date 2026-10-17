"""Embedding + in-process vector index for event retrieval.

Public API:
    EmbeddingModel(model_name=...)   # local sentence-transformers wrapper
    VectorIndex()                    # numpy top-k cosine index
    build_index(events, model=...)   # chunk -> embed -> index (one call)
"""

from .model import EmbeddingModel, DEFAULT_MODEL
from .index import VectorIndex
from .builder import build_index

__all__ = ["EmbeddingModel", "VectorIndex", "build_index", "DEFAULT_MODEL"]
