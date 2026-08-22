#!/usr/bin/env python3
"""Query the RAG v1 pipeline from the command line."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.generation.openai_llm import OpenAILLM
from cloudops_rag.generation.rag_service import RagService
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python scripts/query.py "Why is my Kubernetes Pod not becoming ready?"')
        return 2

    question = " ".join(sys.argv[1:]).strip()
    settings = Settings.from_env()
    embedder = OpenAIEmbedder(model=settings.embedding_model, api_key=settings.openai_api_key)
    llm = OpenAILLM(model=settings.llm_model, api_key=settings.openai_api_key)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)
    service = RagService(store, embedder, llm, top_k=settings.retrieval_top_k)
    result = service.query(question)

    print(f"Question: {result.question}\n")
    print("Answer:")
    print(result.answer)
    print("\nRetrieved Sources:")
    for source in result.sources:
        print(f"- rank={source.rank} doc_id={source.doc_id} title={source.title}")
        print(f"  {source.source_url}")
    print("\nRetrieved Chunks:")
    for chunk in result.retrieved_chunks:
        print(f"- rank={chunk.rank} doc_id={chunk.doc_id} chunk_id={chunk.chunk_id} score={chunk.score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

