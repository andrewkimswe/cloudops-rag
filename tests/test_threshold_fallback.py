from __future__ import annotations

from dataclasses import dataclass

from cloudops_rag.generation.rag_service import RagService
from cloudops_rag.retrieval.schemas import RetrievedChunk


def make_chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        doc_id="k8s_debug_pods",
        title="Debug Pods",
        source_url="https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
        provider="kubernetes",
        category="pod_troubleshooting",
        chunk_id="k8s_debug_pods::0000",
        chunk="debug pod content",
        score=score,
    )


@dataclass
class FakeVectorStore:
    score: float

    def retrieve(self, question, embedder, top_k):
        return [make_chunk(self.score)]


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def answer(self, question, retrieved_chunks):
        self.calls += 1
        return "grounded answer"


def test_fallback_skips_llm_and_returns_no_sources():
    llm = FakeLLM()
    service = RagService(
        vector_store=FakeVectorStore(score=1.2),
        embedder=object(),
        llm=llm,
        top_k=5,
        distance_threshold=1.04,
    )

    result = service.query("out of scope question")

    assert result.fallback is True
    assert result.sources == []
    assert result.retrieval_distance == 1.2
    assert result.distance_threshold == 1.04
    assert llm.calls == 0


def test_accept_calls_llm_and_returns_sources():
    llm = FakeLLM()
    service = RagService(
        vector_store=FakeVectorStore(score=0.8),
        embedder=object(),
        llm=llm,
        top_k=5,
        distance_threshold=1.04,
    )

    result = service.query("in scope question")

    assert result.fallback is False
    assert result.answer == "grounded answer"
    assert [source.doc_id for source in result.sources] == ["k8s_debug_pods"]
    assert result.retrieval_distance == 0.8
    assert llm.calls == 1
