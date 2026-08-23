from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("prometheus_client")

from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from cloudops_rag.api.app import create_app
from cloudops_rag.generation.rag_service import RagService
from cloudops_rag.ingestion.document_service import DocumentStatusRecord, IngestionResult
from cloudops_rag.retrieval.schemas import RetrievedChunk


def metric_value(name: str, labels: dict[str, str] | None = None) -> float:
    labels = labels or {}
    text = generate_latest().decode("utf-8")
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name == name and all(sample.labels.get(key) == value for key, value in labels.items()):
                return float(sample.value)
    return 0.0


def make_chunk(score: float = 0.7) -> RetrievedChunk:
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


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [1.0]


class FailingEmbedder:
    def __init__(self, exc: Exception):
        self.exc = exc

    def embed_query(self, text: str) -> list[float]:
        raise self.exc


class FailingLLM:
    def __init__(self, exc: Exception):
        self.exc = exc

    def answer(self, question: str, retrieved_chunks: list[RetrievedChunk]) -> str:
        raise self.exc


class FakeVectorStore:
    def __init__(self, score: float = 0.7):
        self.score = score

    def retrieve_by_embedding(self, query_embedding: list[float], top_k: int):
        return [make_chunk(self.score)]


class FakeLLM:
    def answer(self, question: str, retrieved_chunks: list[RetrievedChunk]) -> str:
        return "grounded answer"


def test_query_metrics_increment_for_answered_request():
    before_query = metric_value("cloudops_rag_query_requests_total", {"result": "answered"})
    before_generation = metric_value("cloudops_rag_generation_duration_seconds_count")

    service = RagService(
        vector_store=FakeVectorStore(score=0.7),
        embedder=FakeEmbedder(),
        llm=FakeLLM(),
        top_k=5,
        distance_threshold=1.042478,
    )

    result = service.query("Why is my Pod Pending?")

    assert result.fallback is False
    assert metric_value("cloudops_rag_query_requests_total", {"result": "answered"}) == before_query + 1
    assert metric_value("cloudops_rag_generation_duration_seconds_count") == before_generation + 1


def test_embedding_failure_records_query_error_and_openai_metric():
    before_query_error = metric_value("cloudops_rag_query_requests_total", {"result": "error"})
    before_openai_embedding = metric_value("cloudops_rag_openai_failures_total", {"operation": "embedding"})

    service = RagService(
        vector_store=FakeVectorStore(score=0.7),
        embedder=FailingEmbedder(RuntimeError("embedding failed")),
        llm=FakeLLM(),
        top_k=5,
        distance_threshold=1.042478,
    )

    with pytest.raises(RuntimeError):
        service.query("embedding failure")

    assert metric_value("cloudops_rag_query_requests_total", {"result": "error"}) == before_query_error + 1
    assert metric_value("cloudops_rag_openai_failures_total", {"operation": "embedding"}) == before_openai_embedding + 1


def test_generation_failure_records_query_error_and_openai_metric():
    before_query_error = metric_value("cloudops_rag_query_requests_total", {"result": "error"})
    before_openai_generation = metric_value("cloudops_rag_openai_failures_total", {"operation": "generation"})
    before_generation = metric_value("cloudops_rag_generation_duration_seconds_count")

    service = RagService(
        vector_store=FakeVectorStore(score=0.7),
        embedder=FakeEmbedder(),
        llm=FailingLLM(RuntimeError("generation failed")),
        top_k=5,
        distance_threshold=1.042478,
    )

    with pytest.raises(RuntimeError):
        service.query("generation failure")

    assert metric_value("cloudops_rag_query_requests_total", {"result": "error"}) == before_query_error + 1
    assert metric_value("cloudops_rag_openai_failures_total", {"operation": "generation"}) == before_openai_generation + 1
    assert metric_value("cloudops_rag_generation_duration_seconds_count") == before_generation + 1


def test_fallback_metrics_increment_without_generation_observation():
    before_query = metric_value("cloudops_rag_query_requests_total", {"result": "fallback"})
    before_fallback = metric_value("cloudops_rag_fallback_total")
    before_generation = metric_value("cloudops_rag_generation_duration_seconds_count")

    service = RagService(
        vector_store=FakeVectorStore(score=1.5),
        embedder=FakeEmbedder(),
        llm=FakeLLM(),
        top_k=5,
        distance_threshold=1.042478,
    )

    result = service.query("out of scope question")

    assert result.fallback is True
    assert metric_value("cloudops_rag_query_requests_total", {"result": "fallback"}) == before_query + 1
    assert metric_value("cloudops_rag_fallback_total") == before_fallback + 1
    assert metric_value("cloudops_rag_generation_duration_seconds_count") == before_generation


class FakeCollection:
    def count(self) -> int:
        return 1


class FakeAppVectorStore:
    collection_name = "cloudops_rag_runtime_openai_text_embedding_3_small"
    collection = FakeCollection()


class FakeRagService:
    top_k = 5

    def query(self, question: str):
        return SimpleNamespace(
            question=question,
            answer="grounded answer",
            fallback=False,
            sources=[],
            retrieved_chunks=[make_chunk()],
            retrieval_distance=0.7,
            distance_threshold=1.042478,
        )


class FakeIngestionService:
    def __init__(self):
        self.records = {}

    def ingest(self, source_url: str, title: str | None = None, provider: str | None = None, category: str | None = None):
        if "failure" in source_url:
            record = DocumentStatusRecord(
                doc_id="registered_failure",
                status="failed",
                source_url=source_url,
                title=title,
                provider=provider,
                category=category,
                created_at="2026-08-22T00:00:00Z",
                updated_at="2026-08-22T00:00:01Z",
                message="Document fetch failed.",
                error_code="fetch_failed",
            )
            self.records[record.doc_id] = record
            return IngestionResult(record=record)
        duplicate = "duplicate" in source_url
        record = DocumentStatusRecord(
            doc_id="registered_success",
            status="completed",
            source_url=source_url,
            title=title or "Runtime Doc",
            provider=provider or "runtime",
            category=category or "runtime_document",
            created_at="2026-08-22T00:00:00Z",
            updated_at="2026-08-22T00:00:01Z",
            message="Document ingestion completed.",
            chunk_count=1,
            processed_chars=500,
        )
        self.records[record.doc_id] = record
        return IngestionResult(record=record, duplicate=duplicate)

    def get_status(self, doc_id: str):
        return self.records.get(doc_id)


def make_client(monkeypatch) -> TestClient:
    ingestion_service = FakeIngestionService()

    def fake_build_api_state():
        return SimpleNamespace(
            vector_store=FakeAppVectorStore(),
            rag_service=FakeRagService(),
            ingestion_service=ingestion_service,
            documents={
                "k8s_debug_pods": {
                    "doc_id": "k8s_debug_pods",
                    "title": "Debug Pods",
                    "source_url": "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
                    "status": "pending",
                    "message": "Registered in manifest.",
                }
            },
        )

    monkeypatch.setattr("cloudops_rag.api.app.build_api_state", fake_build_api_state)
    app = create_app()
    app.state.api_state = fake_build_api_state()
    return TestClient(app)


def test_metrics_endpoint_returns_prometheus_text(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "cloudops_rag_http_requests_total" in response.text


def test_http_metrics_use_bounded_route_template(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/documents/k8s_debug_pods/status")
    metrics_response = client.get("/metrics")

    assert response.status_code == 200
    assert 'endpoint="/documents/{doc_id}/status"' in metrics_response.text
    assert 'endpoint="/documents/k8s_debug_pods/status"' not in metrics_response.text


def test_ingestion_metrics_increment_for_success_duplicate_and_failure(monkeypatch):
    client = make_client(monkeypatch)
    before_completed = metric_value("cloudops_rag_ingestion_requests_total", {"result": "completed"})
    before_duplicate = metric_value("cloudops_rag_ingestion_requests_total", {"result": "duplicate"})
    before_failed = metric_value("cloudops_rag_ingestion_requests_total", {"result": "failed"})
    before_fetch_failed = metric_value("cloudops_rag_ingestion_failures_total", {"reason": "fetch_failed"})

    completed = client.post("/documents", json={"source_url": "https://example.com/success"})
    duplicate = client.post("/documents", json={"source_url": "https://example.com/duplicate"})
    failed = client.post("/documents", json={"source_url": "https://example.com/failure"})

    assert completed.status_code == 200
    assert duplicate.status_code == 200
    assert failed.status_code == 400
    assert metric_value("cloudops_rag_ingestion_requests_total", {"result": "completed"}) == before_completed + 1
    assert metric_value("cloudops_rag_ingestion_requests_total", {"result": "duplicate"}) == before_duplicate + 1
    assert metric_value("cloudops_rag_ingestion_requests_total", {"result": "failed"}) == before_failed + 1
    assert metric_value("cloudops_rag_ingestion_failures_total", {"reason": "fetch_failed"}) == before_fetch_failed + 1


def test_repeated_app_initialization_does_not_duplicate_metric_registration(monkeypatch):
    client_1 = make_client(monkeypatch)
    client_2 = make_client(monkeypatch)

    assert client_1.get("/metrics").status_code == 200
    assert client_2.get("/metrics").status_code == 200
