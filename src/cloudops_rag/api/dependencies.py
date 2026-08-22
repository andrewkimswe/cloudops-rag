"""FastAPI dependency setup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request

from cloudops_rag.api.config import (
    DEFAULT_OPENAI_EMBEDDING_TIMEOUT_SECONDS,
    DEFAULT_OPENAI_LLM_TIMEOUT_SECONDS,
    FROZEN_CHROMA_COLLECTION,
    FROZEN_CHUNK_OVERLAP,
    FROZEN_CHUNK_SIZE,
    FROZEN_EVALUATION_CHROMA_COLLECTION,
    FROZEN_EMBEDDING_MODEL,
    FROZEN_LLM_MODEL,
    FROZEN_RETRIEVAL_TOP_K,
    FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
)
from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.generation.openai_llm import OpenAILLM
from cloudops_rag.generation.rag_service import RagService
from cloudops_rag.ingestion.document_service import DocumentIngestionService, JsonDocumentRegistry
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore


@dataclass
class ApiState:
    settings: Settings
    vector_store: ChromaVectorStore
    rag_service: RagService
    ingestion_service: DocumentIngestionService
    documents: dict[str, dict[str, Any]]


def build_api_state(settings: Settings | None = None) -> ApiState:
    settings = settings or Settings.from_env()
    embedder = OpenAIEmbedder(
        model=FROZEN_EMBEDDING_MODEL,
        api_key=settings.openai_api_key,
        timeout=DEFAULT_OPENAI_EMBEDDING_TIMEOUT_SECONDS,
    )
    llm = OpenAILLM(
        model=FROZEN_LLM_MODEL,
        api_key=settings.openai_api_key,
        timeout=DEFAULT_OPENAI_LLM_TIMEOUT_SECONDS,
    )
    vector_store = ChromaVectorStore(settings.chroma_persist_dir, FROZEN_CHROMA_COLLECTION)
    seed_runtime_collection_if_empty(settings.chroma_persist_dir, vector_store)
    rag_service = RagService(
        vector_store=vector_store,
        embedder=embedder,
        llm=llm,
        top_k=FROZEN_RETRIEVAL_TOP_K,
        distance_threshold=FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
    )
    registry = JsonDocumentRegistry(settings.runtime_status_path)
    ingestion_service = DocumentIngestionService(
        registry=registry,
        vector_store=vector_store,
        embedder=embedder,
        raw_dir=settings.raw_dir,
        processed_dir=settings.processed_dir,
        chunk_size=FROZEN_CHUNK_SIZE,
        chunk_overlap=FROZEN_CHUNK_OVERLAP,
    )
    return ApiState(
        settings=settings,
        vector_store=vector_store,
        rag_service=rag_service,
        ingestion_service=ingestion_service,
        documents=load_document_registry(settings.manifest_path),
    )


def seed_runtime_collection_if_empty(persist_dir: Path, runtime_store: ChromaVectorStore) -> None:
    if runtime_store.collection.count() > 0:
        return
    if runtime_store.collection_name == FROZEN_EVALUATION_CHROMA_COLLECTION:
        return
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(persist_dir))
        source = client.get_collection(FROZEN_EVALUATION_CHROMA_COLLECTION)
    except Exception:
        return

    total = source.count()
    if total == 0:
        return
    batch_size = 128
    for offset in range(0, total, batch_size):
        batch = source.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas", "embeddings"],
        )
        ids = batch.get("ids", [])
        if not ids:
            continue
        runtime_store.collection.upsert(
            ids=ids,
            documents=batch.get("documents"),
            metadatas=batch.get("metadatas"),
            embeddings=batch.get("embeddings"),
        )


def load_document_registry(manifest_path: Path) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    if not manifest_path.exists():
        return registry
    for doc in load_manifest(manifest_path):
        registry[doc.doc_id] = {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "source_url": doc.source_url,
            "status": "pending",
            "message": "Document is registered in the corpus manifest. Phase 16 will expand ingestion status handling.",
        }
    return registry


def get_api_state(request: Request) -> ApiState:
    return request.app.state.api_state
