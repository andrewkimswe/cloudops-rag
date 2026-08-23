"""OpenAI embedding provider."""

from __future__ import annotations


class OpenAIEmbedder:
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAI embeddings") from exc
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        self.model = model
        self.client = OpenAI(api_key=api_key, timeout=timeout)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
        except Exception as exc:
            if is_timeout_error(exc):
                raise TimeoutError("OpenAI embedding request timed out") from exc
            raise RuntimeError("OpenAI embedding request failed") from exc
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def is_timeout_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"APITimeoutError", "Timeout", "ReadTimeout", "ConnectTimeout"}
