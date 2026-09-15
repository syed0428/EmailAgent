"""
Embedding Service
─────────────────
Supports two backends:
  1. sentence_transformers  – runs locally via SentenceTransformers (default)
  2. ollama                 – calls Ollama /api/embeddings endpoint

Backend is selected via EMBEDDING_BACKEND env variable.
"""

import logging
import os
import sys

# Disable HuggingFace tokenizer parallelism to prevent fork conflicts
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from typing import List
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    def __init__(self):
        self.backend = settings.embedding_backend
        self._st_model = None   # lazy-loaded SentenceTransformer

    def _get_st_model(self):
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer
            model_name = settings.sentence_transformer_model
            logger.info(f"Loading SentenceTransformer model: {model_name}")
            self._st_model = SentenceTransformer(model_name)
        return self._st_model

    def _encode(self, model, sentences, **kwargs):
        """Encode with tqdm disabled to avoid Windows Errno 22 in thread pool."""
        import numpy as np
        # Disable tqdm entirely by passing a null file
        return model.encode(
            sentences,
            show_progress_bar=False,
            normalize_embeddings=kwargs.get("normalize_embeddings", True),
        )

    def embed(self, text: str) -> List[float]:
        """Generate a single embedding for the given text."""
        text = text.strip()
        if not text:
            raise ValueError("Cannot embed empty text")

        if self.backend == "sentence_transformers":
            return self._embed_sentence_transformers(text)
        elif self.backend == "ollama":
            return self._embed_ollama(text)
        else:
            raise ValueError(f"Unknown embedding backend: {self.backend}")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts at once (more efficient for ST backend)."""
        texts = [t.strip() for t in texts if t.strip()]
        if not texts:
            return []

        if self.backend == "sentence_transformers":
            model = self._get_st_model()
            vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            return [v.tolist() for v in vectors]
        else:
            return [self.embed(t) for t in texts]

    def _embed_sentence_transformers(self, text: str) -> List[float]:
        model = self._get_st_model()
        vector = model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()

    def _embed_ollama(self, text: str) -> List[float]:
        import httpx
        payload = {"model": settings.embedding_model, "prompt": text}
        try:
            resp = httpx.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as exc:
            logger.error(f"Ollama embedding failed: {exc}")
            raise

    @property
    def model_name(self) -> str:
        if self.backend == "sentence_transformers":
            return settings.sentence_transformer_model
        return settings.embedding_model


@lru_cache()
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
