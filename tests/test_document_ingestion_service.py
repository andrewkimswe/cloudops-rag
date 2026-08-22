from __future__ import annotations

from pathlib import Path

from cloudops_rag.ingestion.document_service import DocumentIngestionService, JsonDocumentRegistry, stable_document_id
from cloudops_rag.ingestion.fetch import FetchResult


HTML = """
<html>
  <head><title>Runtime Probe Troubleshooting</title></head>
  <body>
    <main>
      <h1>Runtime Probe Troubleshooting</h1>
      <p>Unique runtime ingestion marker alpha beta gamma.</p>
      <p>Check startup probes before liveness probes when slow applications initialize.</p>
    </main>
  </body>
</html>
"""


class FakeEmbedder:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding failed")
        return [[float(len(text)), 0.1, 0.2] for text in texts]


class FakeVectorStore:
    collection_name = "test_runtime"

    def __init__(self, fail_index: bool = False):
        self.fail_index = fail_index
        self.ids: set[str] = set()
        self.deleted: list[str] = []

    def delete_document_chunks(self, doc_id: str) -> int:
        matching = {chunk_id for chunk_id in self.ids if chunk_id.startswith(f"{doc_id}::")}
        self.ids -= matching
        self.deleted.append(doc_id)
        return len(matching)

    def upsert_chunks_with_embeddings(self, chunks, embeddings, batch_size: int = 64) -> int:
        if self.fail_index:
            self.ids.add(chunks[0].chunk_id)
            raise RuntimeError("index failed")
        for chunk in chunks:
            self.ids.add(chunk.chunk_id)
        return len(chunks)

    def count_document_chunks(self, doc_id: str) -> int:
        return sum(1 for chunk_id in self.ids if chunk_id.startswith(f"{doc_id}::"))


def fetcher(url: str) -> FetchResult:
    return FetchResult(source_url=url, final_url=url, content_type="text/html", body=HTML)


def make_service(tmp_path: Path, vector_store: FakeVectorStore | None = None, embedder: FakeEmbedder | None = None):
    return DocumentIngestionService(
        registry=JsonDocumentRegistry(tmp_path / "document_status.json"),
        vector_store=vector_store or FakeVectorStore(),
        embedder=embedder or FakeEmbedder(),
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        chunk_size=128,
        chunk_overlap=0,
        fetcher=fetcher,
    )


def test_valid_document_ingestion_persists_completed_status(tmp_path):
    service = make_service(tmp_path)
    result = service.ingest("https://example.com/runtime-probe")

    assert result.record.status == "completed"
    assert result.record.chunk_count and result.record.chunk_count > 0
    assert result.record.processed_chars and result.record.processed_chars > 100
    assert result.record.timings_ms["total_ms"] >= 0

    reloaded = JsonDocumentRegistry(tmp_path / "document_status.json")
    assert reloaded.get(result.record.doc_id).status == "completed"


def test_duplicate_completed_document_does_not_reembed_or_add_chunks(tmp_path):
    embedder = FakeEmbedder()
    vector_store = FakeVectorStore()
    service = make_service(tmp_path, vector_store=vector_store, embedder=embedder)

    first = service.ingest("https://example.com/runtime-probe")
    first_count = vector_store.count_document_chunks(first.record.doc_id)
    second = service.ingest("https://example.com/runtime-probe")

    assert second.duplicate is True
    assert embedder.calls == 1
    assert vector_store.count_document_chunks(first.record.doc_id) == first_count


def test_partial_index_failure_marks_failed_and_cleans_chunks(tmp_path):
    vector_store = FakeVectorStore(fail_index=True)
    service = make_service(tmp_path, vector_store=vector_store)
    result = service.ingest("https://example.com/runtime-probe")
    doc_id = stable_document_id("https://example.com/runtime-probe")

    assert result.record.status == "failed"
    assert result.record.error_code == "indexing_failed"
    assert vector_store.count_document_chunks(doc_id) == 0
    assert doc_id in vector_store.deleted
