"""Chroma indexing and retrieval helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from cloudops_rag.chunking.chunker import DocumentChunk
from cloudops_rag.retrieval.schemas import RetrievedChunk


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class ChromaVectorStore:
    def __init__(self, persist_dir: Path, collection_name: str):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("chromadb package is required for Chroma indexing") from exc

        persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def reset_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def index_chunks(
        self,
        chunks: list[DocumentChunk],
        embedder: Embedder,
        batch_size: int = 64,
        reset: bool = True,
    ) -> int:
        if reset:
            self.reset_collection()

        indexed = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            texts = [chunk.page_content for chunk in batch]
            embeddings = embedder.embed_documents(texts)
            self.collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=texts,
                metadatas=[chunk.metadata for chunk in batch],
                embeddings=embeddings,
            )
            indexed += len(batch)
        return indexed

    def upsert_chunks_with_embeddings(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        batch_size: int = 64,
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        indexed = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            batch_embeddings = embeddings[start : start + batch_size]
            self.collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.page_content for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
                embeddings=batch_embeddings,
            )
            indexed += len(batch)
        return indexed

    def delete_document_chunks(self, doc_id: str) -> int:
        existing = self.collection.get(where={"doc_id": doc_id}, include=[])
        ids = existing.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def count_document_chunks(self, doc_id: str) -> int:
        existing = self.collection.get(where={"doc_id": doc_id}, include=[])
        return len(existing.get("ids", []))

    def retrieve(self, query: str, embedder: Embedder, top_k: int = 3) -> list[RetrievedChunk]:
        query_embedding = embedder.embed_query(query)
        return self.retrieve_by_embedding(query_embedding, top_k)

    def retrieve_by_embedding(self, query_embedding: list[float], top_k: int = 3) -> list[RetrievedChunk]:
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        retrieved: list[RetrievedChunk] = []
        for index, (text, metadata, distance) in enumerate(zip(documents, metadatas, distances), start=1):
            retrieved.append(
                RetrievedChunk(
                    rank=index,
                    doc_id=str(metadata["doc_id"]),
                    title=str(metadata["title"]),
                    source_url=str(metadata["source_url"]),
                    provider=str(metadata["provider"]),
                    category=str(metadata["category"]),
                    chunk_id=str(metadata["chunk_id"]),
                    chunk=text,
                    score=float(distance) if distance is not None else None,
                )
            )
        return retrieved
