"""Experimental retrieval diversification post-processing helpers."""

from __future__ import annotations

from collections import Counter
from typing import TypeVar

T = TypeVar("T")


def select_with_per_document_cap(
    ranked_chunks: list[T],
    *,
    top_k: int,
    per_document_cap: int,
) -> list[T]:
    """Select ranked chunks while limiting how many chunks each doc_id can occupy.

    The input ranking order is preserved for chunks that pass the cap. This helper is
    experimental and does not alter the production Chroma retrieval path.
    """
    if top_k < 0:
        raise ValueError("top_k must be non-negative")
    if per_document_cap <= 0:
        raise ValueError("per_document_cap must be positive")

    selected: list[T] = []
    counts: Counter[str] = Counter()
    for chunk in ranked_chunks:
        doc_id = str(getattr(chunk, "doc_id"))
        if counts[doc_id] >= per_document_cap:
            continue
        selected.append(chunk)
        counts[doc_id] += 1
        if len(selected) == top_k:
            break
    return selected


def document_diversity(retrieved_doc_ids: list[str]) -> dict[str, float | int]:
    retrieved_count = len(retrieved_doc_ids)
    unique_doc_count = len(set(retrieved_doc_ids))
    duplicate_chunk_count = retrieved_count - unique_doc_count
    duplicate_ratio = duplicate_chunk_count / retrieved_count if retrieved_count else 0.0
    max_same_document_occupancy = max(Counter(retrieved_doc_ids).values(), default=0)
    return {
        "retrieved_chunk_count": retrieved_count,
        "unique_doc_count": unique_doc_count,
        "duplicate_chunk_count": duplicate_chunk_count,
        "duplicate_ratio": duplicate_ratio,
        "max_same_document_occupancy": max_same_document_occupancy,
    }
