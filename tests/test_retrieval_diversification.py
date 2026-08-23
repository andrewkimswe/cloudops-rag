from dataclasses import dataclass

import pytest

from cloudops_rag.retrieval.chroma_store import ChromaVectorStore
from cloudops_rag.retrieval.diversification import document_diversity, select_with_per_document_cap


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str


def ids(chunks: list[Chunk]) -> list[str]:
    return [chunk.chunk_id for chunk in chunks]


def test_cap_2_constraint() -> None:
    ranked = [
        Chunk("doc_a", "a1"),
        Chunk("doc_a", "a2"),
        Chunk("doc_a", "a3"),
        Chunk("doc_b", "b1"),
        Chunk("doc_b", "b2"),
    ]

    selected = select_with_per_document_cap(ranked, top_k=5, per_document_cap=2)

    assert ids(selected) == ["a1", "a2", "b1", "b2"]
    assert sum(chunk.doc_id == "doc_a" for chunk in selected) == 2


def test_ranking_order_preservation() -> None:
    ranked = [
        Chunk("doc_a", "a1"),
        Chunk("doc_b", "b1"),
        Chunk("doc_a", "a2"),
        Chunk("doc_c", "c1"),
        Chunk("doc_b", "b2"),
    ]

    selected = select_with_per_document_cap(ranked, top_k=4, per_document_cap=2)

    assert ids(selected) == ["a1", "b1", "a2", "c1"]


def test_final_top_k_size_when_enough_candidates_exist() -> None:
    ranked = [Chunk(f"doc_{index}", f"c{index}") for index in range(8)]

    selected = select_with_per_document_cap(ranked, top_k=5, per_document_cap=2)

    assert len(selected) == 5


def test_insufficient_unique_docs_case_returns_available_chunks() -> None:
    ranked = [Chunk("doc_a", "a1"), Chunk("doc_a", "a2"), Chunk("doc_a", "a3")]

    selected = select_with_per_document_cap(ranked, top_k=5, per_document_cap=2)

    assert ids(selected) == ["a1", "a2"]


def test_metadata_doc_id_handling_uses_doc_id_attribute() -> None:
    ranked = [Chunk("same_doc", "c1"), Chunk("same_doc", "c2"), Chunk("same_doc", "c3"), Chunk("other", "c4")]

    selected = select_with_per_document_cap(ranked, top_k=5, per_document_cap=2)

    assert [chunk.doc_id for chunk in selected] == ["same_doc", "same_doc", "other"]


def test_document_diversity_metrics() -> None:
    result = document_diversity(["doc_a", "doc_a", "doc_b", "doc_c", "doc_c"])

    assert result["retrieved_chunk_count"] == 5
    assert result["unique_doc_count"] == 3
    assert result["duplicate_chunk_count"] == 2
    assert result["duplicate_ratio"] == 0.4
    assert result["max_same_document_occupancy"] == 2


def test_baseline_retriever_is_unchanged() -> None:
    assert not hasattr(ChromaVectorStore, "per_document_cap")
    assert ChromaVectorStore.retrieve.__name__ == "retrieve"


def test_invalid_cap_inputs() -> None:
    with pytest.raises(ValueError, match="top_k"):
        select_with_per_document_cap([], top_k=-1, per_document_cap=2)
    with pytest.raises(ValueError, match="per_document_cap"):
        select_with_per_document_cap([], top_k=5, per_document_cap=0)
