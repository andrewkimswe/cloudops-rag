"""OpenAI chat completion client for grounded RAG answers."""

from __future__ import annotations

from cloudops_rag.retrieval.schemas import RetrievedChunk


class OpenAILLM:
    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None, timeout: float = 45.0):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAI generation") from exc
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI generation")
        self.model = model
        self.client = OpenAI(api_key=api_key, timeout=timeout)

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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
            )
        except Exception as exc:
            if is_timeout_error(exc):
                raise TimeoutError("OpenAI generation request timed out") from exc
            raise RuntimeError("OpenAI generation request failed") from exc
        return response.choices[0].message.content or ""


def is_timeout_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"APITimeoutError", "Timeout", "ReadTimeout", "ConnectTimeout"}
