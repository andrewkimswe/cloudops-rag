"""Baseline character-based chunking."""

from __future__ import annotations

from dataclasses import dataclass

from cloudops_rag.ingestion.loader import CorpusDocument


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    page_content: str
    metadata: dict[str, str | int]


def chunk_documents(
    documents: list[CorpusDocument],
    chunk_size: int = 512,
    chunk_overlap: int = 0,
) -> list[DocumentChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    chunks: list[DocumentChunk] = []
    step = chunk_size - chunk_overlap

    for document in documents:
        text = document.page_content
        doc_id = str(document.metadata["doc_id"])
        chunk_index = 0
        for start in range(0, len(text), step):
            chunk_text = text[start : start + chunk_size].strip()
            if not chunk_text:
                continue
            chunk_id = f"{doc_id}::{chunk_index:04d}"
            metadata: dict[str, str | int] = {
                **document.metadata,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "chunk_start": start,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "chunk_unit": "character",
            }
            chunks.append(DocumentChunk(chunk_id=chunk_id, page_content=chunk_text, metadata=metadata))
            chunk_index += 1
    return chunks

