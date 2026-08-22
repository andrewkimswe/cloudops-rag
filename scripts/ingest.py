#!/usr/bin/env python3
"""Fetch official docs, clean them, chunk them, and index into Chroma."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.chunking.chunker import chunk_documents
from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.ingestion.fetch import fetch_documents
from cloudops_rag.ingestion.loader import load_processed_documents
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore


def main() -> int:
    settings = Settings.from_env()
    documents = load_manifest(settings.manifest_path)
    successes, failures = fetch_documents(documents, settings.raw_dir, settings.processed_dir)

    print(f"Fetched documents: {len(successes)}/{len(documents)}")
    if failures:
        print("Fetch failures:")
        print(json.dumps(failures, indent=2, ensure_ascii=False))
        return 1

    processed_documents = load_processed_documents(settings.processed_dir)
    chunks = chunk_documents(processed_documents, settings.chunk_size, settings.chunk_overlap)
    print(f"Processed documents: {len(processed_documents)}")
    print(
        f"Chunks: {len(chunks)} "
        f"(chunk_size={settings.chunk_size}, chunk_overlap={settings.chunk_overlap}, unit=character)"
    )

    embedder = OpenAIEmbedder(model=settings.embedding_model, api_key=settings.openai_api_key)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)
    indexed = store.index_chunks(chunks, embedder, reset=True)
    print(f"Indexed chunks: {indexed}")
    print(f"Chroma collection: {settings.chroma_collection}")
    print(f"Chroma persist dir: {settings.chroma_persist_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

