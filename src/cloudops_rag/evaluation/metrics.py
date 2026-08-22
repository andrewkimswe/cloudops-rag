"""Retrieval evaluation metrics for Phase 7 baseline measurement."""

from __future__ import annotations


def first_relevant_rank(expected_doc_ids: set[str], retrieved_doc_ids: list[str]) -> int | None:
    for index, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in expected_doc_ids:
            return index
    return None


def hit_at_k(expected_doc_ids: set[str], retrieved_doc_ids: list[str], k: int) -> bool:
    return any(doc_id in expected_doc_ids for doc_id in retrieved_doc_ids[:k])


def reciprocal_rank(expected_doc_ids: set[str], retrieved_doc_ids: list[str]) -> float:
    rank = first_relevant_rank(expected_doc_ids, retrieved_doc_ids)
    if rank is None:
        return 0.0
    return 1.0 / rank


def multi_any_hit_at_k(expected_doc_ids: set[str], retrieved_doc_ids: list[str], k: int) -> bool:
    return hit_at_k(expected_doc_ids, retrieved_doc_ids, k)


def multi_all_hit_at_k(expected_doc_ids: set[str], retrieved_doc_ids: list[str], k: int) -> bool:
    top_k_doc_ids = set(retrieved_doc_ids[:k])
    return expected_doc_ids.issubset(top_k_doc_ids)


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

