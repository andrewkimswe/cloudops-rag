"""OpenAI chat completion client for grounded RAG answers."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from cloudops_rag.api.metrics import EXTERNAL_RETRIES_TOTAL
from cloudops_rag.retrieval.schemas import RetrievedChunk
from cloudops_rag.resilience.retry import DEFAULT_RETRY_POLICY, RetryPolicy, execute_with_retry, is_timeout_error


class OpenAILLM:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        timeout: float = 45.0,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        retry_sleep: Callable[[float], None] = time.sleep,
        retry_random: Callable[[], float] = random.random,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAI generation") from exc
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI generation")
        self.model = model
        self.retry_policy = retry_policy
        self.retry_sleep = retry_sleep
        self.retry_random = retry_random
        self.client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    def answer(self, question: str, retrieved_chunks: list[RetrievedChunk]) -> str:
        context_blocks = []
        for chunk in retrieved_chunks:
            context_blocks.append(
                f"[rank={chunk.rank} doc_id={chunk.doc_id} title={chunk.title}]\n{chunk.chunk}"
            )
        context = "\n\n---\n\n".join(context_blocks)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a CloudOps troubleshooting assistant. Answer only from the "
                    "provided official documentation context. If the context is insufficient, "
                    "say that the provided official documents do not contain enough evidence."
                ),
            },
            {
                "role": "user",
                "content": f"Question:\n{question}\n\nOfficial documentation context:\n{context}",
            },
        ]
        try:
            response = execute_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                ),
                operation_name="generation",
                policy=getattr(self, "retry_policy", DEFAULT_RETRY_POLICY),
                on_retry=lambda reason: EXTERNAL_RETRIES_TOTAL.labels(
                    operation="generation",
                    reason=reason,
                ).inc(),
                sleep=getattr(self, "retry_sleep", time.sleep),
                random_fn=getattr(self, "retry_random", random.random),
            )
        except Exception as exc:
            if is_timeout_error(exc):
                raise TimeoutError("OpenAI generation request timed out") from exc
            raise RuntimeError("OpenAI generation request failed") from exc
        return response.choices[0].message.content or ""
