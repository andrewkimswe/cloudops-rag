"""Minimal RAG v1 orchestration."""

from __future__ import annotations

from typing import Protocol

from cloudops_rag.retrieval.chroma_store import ChromaVectorStore, Embedder
from cloudops_rag.retrieval.schemas import RagResult, RetrievedChunk, Source


class LLMClient(Protocol):
    def answer(self, question: str, retrieved_chunks: list[RetrievedChunk]) -> str: ...


class RagService:
    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedder: Embedder,
        llm: LLMClient,
        top_k: int = 3,
        distance_threshold: float | None = None,
        fallback_answer: str = "I couldn't find sufficient support for this question in the indexed documents.",
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.llm = llm
        self.top_k = top_k
        self.distance_threshold = distance_threshold
        self.fallback_answer = fallback_answer

    def query(self, question: str) -> RagResult:
        retrieved = self.vector_store.retrieve(question, self.embedder, self.top_k)
        rank_1_distance = retrieved[0].score if retrieved else None
        if self._should_fallback(rank_1_distance):
            return RagResult(
                question=question,
                answer=self.fallback_answer,
                sources=[],
                retrieved_chunks=retrieved,
                fallback=True,
                retrieval_distance=rank_1_distance,
                distance_threshold=self.distance_threshold,
            )
        answer = self.llm.answer(question, retrieved)
        return RagResult(
            question=question,
            answer=answer,
            sources=deduplicate_sources(retrieved),
            retrieved_chunks=retrieved,
            fallback=False,
            retrieval_distance=rank_1_distance,
            distance_threshold=self.distance_threshold,
        )

    def _should_fallback(self, rank_1_distance: float | None) -> bool:
        if self.distance_threshold is None:
            return False
        if rank_1_distance is None:
            return True
        return rank_1_distance > self.distance_threshold


def deduplicate_sources(retrieved_chunks: list[RetrievedChunk]) -> list[Source]:
    seen: set[str] = set()
    sources: list[Source] = []
    for chunk in retrieved_chunks:
        if chunk.doc_id in seen:
            continue
        seen.add(chunk.doc_id)
        sources.append(
            Source(
                doc_id=chunk.doc_id,
                title=chunk.title,
                source_url=chunk.source_url,
                rank=chunk.rank,
            )
        )
    return sources
