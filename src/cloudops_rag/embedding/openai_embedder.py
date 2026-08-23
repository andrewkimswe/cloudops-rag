"""OpenAI embedding provider."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from cloudops_rag.api.metrics import EXTERNAL_RETRIES_TOTAL
from cloudops_rag.resilience.retry import DEFAULT_RETRY_POLICY, RetryPolicy, execute_with_retry, is_timeout_error


class OpenAIEmbedder:
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        timeout: float = 30.0,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        retry_sleep: Callable[[float], None] = time.sleep,
        retry_random: Callable[[], float] = random.random,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAI embeddings") from exc
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        self.model = model
        self.retry_policy = retry_policy
        self.retry_sleep = retry_sleep
        self.retry_random = retry_random
        self.client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            response = execute_with_retry(
                lambda: self.client.embeddings.create(model=self.model, input=texts),
                operation_name="embedding",
                policy=getattr(self, "retry_policy", DEFAULT_RETRY_POLICY),
                on_retry=lambda reason: EXTERNAL_RETRIES_TOTAL.labels(
                    operation="embedding",
                    reason=reason,
                ).inc(),
                sleep=getattr(self, "retry_sleep", time.sleep),
                random_fn=getattr(self, "retry_random", random.random),
            )
        except Exception as exc:
            if is_timeout_error(exc):
                raise TimeoutError("OpenAI embedding request timed out") from exc
            raise RuntimeError("OpenAI embedding request failed") from exc
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
