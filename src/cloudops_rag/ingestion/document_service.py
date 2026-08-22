"""Runtime document ingestion service."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Literal, Protocol

from bs4 import BeautifulSoup

from cloudops_rag.chunking.chunker import DocumentChunk, chunk_documents
from cloudops_rag.ingestion.fetch import FetchResult, fetch_html
from cloudops_rag.ingestion.html_cleaner import html_to_text
from cloudops_rag.ingestion.loader import CorpusDocument


DocumentStatus = Literal["pending", "processing", "completed", "failed"]


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class MutableVectorStore(Protocol):
    collection_name: str

    def delete_document_chunks(self, doc_id: str) -> int: ...

    def upsert_chunks_with_embeddings(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        batch_size: int = 64,
    ) -> int: ...

    def count_document_chunks(self, doc_id: str) -> int: ...


@dataclass
class DocumentStatusRecord:
    doc_id: str
    status: DocumentStatus
    source_url: str
    title: str | None
    provider: str | None
    category: str | None
    created_at: str
    updated_at: str
    message: str | None = None
    error_code: str | None = None
    chunk_count: int | None = None
    processed_chars: int | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionResult:
    record: DocumentStatusRecord
    duplicate: bool = False


def stable_document_id(source_url: str) -> str:
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
    return f"registered_{digest}"


def utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class JsonDocumentRegistry:
    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, DocumentStatusRecord] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.records = {}
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.records = {
            doc_id: DocumentStatusRecord(**record)
            for doc_id, record in data.get("documents", {}).items()
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"documents": {doc_id: asdict(record) for doc_id, record in sorted(self.records.items())}}
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp_path.replace(self.path)

    def get(self, doc_id: str) -> DocumentStatusRecord | None:
        return self.records.get(doc_id)

    def upsert(self, record: DocumentStatusRecord) -> DocumentStatusRecord:
        self.records[record.doc_id] = record
        self.save()
        return record


class DocumentIngestionService:
    def __init__(
        self,
        registry: JsonDocumentRegistry,
        vector_store: MutableVectorStore,
        embedder: Embedder,
        raw_dir: Path,
        processed_dir: Path,
        chunk_size: int,
        chunk_overlap: int,
        fetcher: Callable[[str], FetchResult] | None = None,
    ):
        self.registry = registry
        self.vector_store = vector_store
        self.embedder = embedder
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.fetcher = fetcher or (lambda url: fetch_html(url, timeout=30))

    def get_status(self, doc_id: str) -> DocumentStatusRecord | None:
        return self.registry.get(doc_id)

    def ingest(
        self,
        source_url: str,
        title: str | None = None,
        provider: str | None = None,
        category: str | None = None,
    ) -> IngestionResult:
        doc_id = stable_document_id(source_url)
        existing = self.registry.get(doc_id)
        if existing and existing.status == "completed":
            return IngestionResult(record=existing, duplicate=True)

        now = utc_now_iso()
        record = DocumentStatusRecord(
            doc_id=doc_id,
            status="pending",
            source_url=source_url,
            title=title,
            provider=provider or "runtime",
            category=category or "runtime_document",
            created_at=existing.created_at if existing else now,
            updated_at=now,
            message="Document ingestion registered.",
        )
        self.registry.upsert(record)

        record.status = "processing"
        record.updated_at = utc_now_iso()
        record.message = "Document ingestion is processing."
        self.registry.upsert(record)

        timings: dict[str, float] = {}
        try:
            fetch_started = time.perf_counter()
            fetched = self.fetcher(source_url)
            timings["fetch_ms"] = elapsed_ms(fetch_started)

            parse_started = time.perf_counter()
            resolved_title = title or extract_html_title(fetched.body) or source_url
            cleaned = html_to_text(fetched.body, resolved_title)
            if len(cleaned.strip()) < 100:
                raise ValueError("parsed document has too little text content")
            timings["parse_ms"] = elapsed_ms(parse_started)

            self._write_runtime_files(doc_id, fetched.body, cleaned, record, resolved_title)

            chunk_started = time.perf_counter()
            document = CorpusDocument(
                page_content=cleaned,
                metadata={
                    "doc_id": doc_id,
                    "title": resolved_title,
                    "provider": record.provider or "runtime",
                    "category": record.category or "runtime_document",
                    "source_url": source_url,
                },
            )
            chunks = chunk_documents([document], self.chunk_size, self.chunk_overlap)
            if not chunks:
                raise ValueError("document produced no chunks")
            timings["chunk_ms"] = elapsed_ms(chunk_started)

            embedding_started = time.perf_counter()
            embeddings = self.embedder.embed_documents([chunk.page_content for chunk in chunks])
            timings["embedding_ms"] = elapsed_ms(embedding_started)

            index_started = time.perf_counter()
            self.vector_store.delete_document_chunks(doc_id)
            self.vector_store.upsert_chunks_with_embeddings(chunks, embeddings)
            indexed_count = self.vector_store.count_document_chunks(doc_id)
            if indexed_count != len(chunks):
                raise RuntimeError("indexed chunk count did not match generated chunk count")
            timings["index_ms"] = elapsed_ms(index_started)

            timings["total_ms"] = sum(timings.values())
            record.status = "completed"
            record.title = resolved_title
            record.chunk_count = len(chunks)
            record.processed_chars = len(cleaned)
            record.timings_ms = timings
            record.updated_at = utc_now_iso()
            record.error_code = None
            record.message = "Document ingestion completed."
            self.registry.upsert(record)
            return IngestionResult(record=record)
        except Exception as exc:
            self._cleanup_partial_chunks(doc_id)
            record.status = "failed"
            record.updated_at = utc_now_iso()
            record.error_code = error_code_for_exception(exc)
            record.message = safe_error_message(exc)
            record.timings_ms = timings
            self.registry.upsert(record)
            return IngestionResult(record=record)

    def _cleanup_partial_chunks(self, doc_id: str) -> None:
        try:
            self.vector_store.delete_document_chunks(doc_id)
        except Exception:
            pass

    def _write_runtime_files(
        self,
        doc_id: str,
        html: str,
        cleaned: str,
        record: DocumentStatusRecord,
        title: str,
    ) -> None:
        raw_path = self.raw_dir / "runtime" / f"{doc_id}.html"
        processed_path = self.processed_dir / "runtime" / f"{doc_id}.md"
        metadata_path = self.processed_dir / "runtime" / f"{doc_id}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html, encoding="utf-8")
        processed_path.write_text(cleaned, encoding="utf-8")
        metadata = {
            "doc_id": doc_id,
            "title": title,
            "provider": record.provider,
            "category": record.category,
            "source_url": record.source_url,
            "raw_path": str(raw_path),
            "processed_path": str(processed_path),
            "runtime_ingestion": True,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def extract_html_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(" ", strip=True)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    return None


def error_code_for_exception(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "fetch_timeout"
    if isinstance(exc, urllib.error.URLError):
        return "fetch_failed"
    if isinstance(exc, ValueError):
        message = str(exc)
        if "content type" in message:
            return "invalid_content"
        if "URL" in message or "scheme" in message:
            return "invalid_url"
        return "parsing_failed"
    if isinstance(exc, RuntimeError):
        return "indexing_failed"
    return "ingestion_failed"


def safe_error_message(exc: Exception) -> str:
    code = error_code_for_exception(exc)
    messages = {
        "fetch_timeout": "Document fetch timed out.",
        "fetch_failed": "Document fetch failed.",
        "invalid_content": "Document content is not supported HTML.",
        "invalid_url": "Document URL is invalid or unsupported.",
        "parsing_failed": "Document parsing or cleaning failed.",
        "indexing_failed": "Document indexing failed.",
        "ingestion_failed": "Document ingestion failed.",
    }
    return messages.get(code, "Document ingestion failed.")
