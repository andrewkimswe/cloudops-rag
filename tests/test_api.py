from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from cloudops_rag.api.app import create_app
from cloudops_rag.ingestion.document_service import DocumentStatusRecord, IngestionResult
from cloudops_rag.retrieval.schemas import RagResult, RetrievedChunk, Source


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


class FakeCollection:
    def count(self) -> int:
        return 483


class FakeVectorStore:
    collection_name = "cloudops_rag_v1_embedding_openai_text_embedding_3_small"
    collection = FakeCollection()


class FakeRagService:
    top_k = 5

    def __init__(self):
        self.calls = 0

    def query(self, question: str) -> RagResult:
        self.calls += 1
        if "fail generation" in question:
            raise RuntimeError("generation failed")
        if "out of scope" in question:
            return RagResult(
                question=question,
                answer="I couldn't find sufficient support for this question in the indexed documents.",
                sources=[],
                retrieved_chunks=[make_chunk(score=1.5)],
                fallback=True,
                retrieval_distance=1.5,
                distance_threshold=1.042478,
            )
        return RagResult(
            question=question,
            answer="Use kubectl describe pod and inspect scheduling events.",
            sources=[
                Source(
                    doc_id="k8s_debug_pods",
                    title="Debug Pods",
                    source_url="https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
                    rank=1,
                )
            ],
            retrieved_chunks=[make_chunk()],
            fallback=False,
            retrieval_distance=0.7,
            distance_threshold=1.042478,
        )


class FakeIngestionService:
    def __init__(self):
        self.records = {
            "k8s_debug_pods": DocumentStatusRecord(
                doc_id="k8s_debug_pods",
                status="pending",
                title="Debug Pods",
                source_url="https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
                provider="kubernetes",
                category="pod_troubleshooting",
                created_at="2026-08-22T00:00:00Z",
                updated_at="2026-08-22T00:00:00Z",
                message="Registered in manifest.",
            )
        }

    def ingest(self, source_url: str, title: str | None = None, provider: str | None = None, category: str | None = None):
        if "fetch-failure" in source_url:
            record = DocumentStatusRecord(
                doc_id="registered_fetch_failure",
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
            doc_id="registered_new_doc",
            status="completed",
            source_url=source_url,
            title=title or "New Doc",
            provider=provider or "example",
            category=category or "test",
            created_at="2026-08-22T00:00:00Z",
            updated_at="2026-08-22T00:00:02Z",
            message="Document ingestion completed.",
            chunk_count=2,
            processed_chars=1500,
            timings_ms={
                "fetch_ms": 1.0,
                "parse_ms": 2.0,
                "chunk_ms": 3.0,
                "embedding_ms": 4.0,
                "index_ms": 5.0,
                "total_ms": 15.0,
            },
        )
        self.records[record.doc_id] = record
        return IngestionResult(record=record, duplicate=duplicate)

    def get_status(self, doc_id: str):
        return self.records.get(doc_id)


def make_client(monkeypatch) -> tuple[TestClient, FakeRagService]:
    service = FakeRagService()
    ingestion_service = FakeIngestionService()

    def fake_build_api_state():
        return SimpleNamespace(
            vector_store=FakeVectorStore(),
            rag_service=service,
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
    return TestClient(app), service


def test_health_returns_chroma_status(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["indexed_chunk_count"] == 483


def test_query_in_scope_returns_answer_sources_and_debug(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post("/query", json={"question": "Why is my Pod Pending?", "debug": True})
    body = response.json()
    assert response.status_code == 200
    assert body["fallback"] is False
    assert body["sources"][0]["doc_id"] == "k8s_debug_pods"
    assert body["debug"]["top_1_distance"] == 0.7


def test_query_out_of_scope_returns_fallback_without_sources(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post("/query", json={"question": "out of scope laptop buying advice"})
    body = response.json()
    assert response.status_code == 200
    assert body["fallback"] is True
    assert body["sources"] == []


def test_empty_question_returns_standard_error(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post("/query", json={"question": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_generation_failure_returns_dependency_error(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post("/query", json={"question": "fail generation"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "external_dependency_unavailable"


def test_document_registration_and_status(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post(
        "/documents",
        json={
            "source_url": "https://example.com/new-doc",
            "title": "New Doc",
            "provider": "example",
            "category": "test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["chunk_count"] == 2
    assert body["processed_chars"] == 1500

    status_response = client.get(f"/documents/{body['doc_id']}/status")
    assert status_response.status_code == 200
    assert status_response.json()["doc_id"] == body["doc_id"]
    assert status_response.json()["status"] == "completed"


def test_duplicate_document_returns_existing_completed_record(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post(
        "/documents",
        json={
            "source_url": "https://example.com/duplicate",
            "title": "Duplicate Doc",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["duplicate"] is True


def test_fetch_failure_returns_standard_error_and_failed_status(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.post(
        "/documents",
        json={
            "source_url": "https://example.com/fetch-failure",
            "title": "Broken Doc",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "fetch_failed"

    status_response = client.get("/documents/registered_fetch_failure/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"
    assert status_response.json()["error_code"] == "fetch_failed"


def test_document_status_not_found(monkeypatch):
    client, _ = make_client(monkeypatch)
    response = client.get("/documents/missing/status")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"
