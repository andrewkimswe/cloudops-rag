"""Local Sentence Transformers embedding provider."""

from __future__ import annotations

import os
from pathlib import Path


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers package is required for local embeddings") from exc
        self.model_name = model_name
        cache_dir = os.getenv("SENTENCE_TRANSFORMERS_HOME")
        if cache_dir is None:
            cache_dir = str(Path("work") / "hf-cache")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", cache_dir)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(cache_dir) / "hub"))
        os.environ.setdefault("HF_XET_CACHE", str(Path(cache_dir) / "xet"))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        self.model = SentenceTransformer(model_name, cache_folder=cache_dir)

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
