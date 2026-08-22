"""Retrieval and RAG result schemas."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int
    doc_id: str
    title: str
    source_url: str
    provider: str
    category: str
    chunk_id: str
    chunk: str
    score: float | None


@dataclass(frozen=True)
class Source:
    doc_id: str
    title: str
    source_url: str
    rank: int


@dataclass(frozen=True)
class RagResult:
    question: str
    answer: str
    sources: list[Source]
    retrieved_chunks: list[RetrievedChunk]
    fallback: bool = False
    retrieval_distance: float | None = None
    distance_threshold: float | None = None
