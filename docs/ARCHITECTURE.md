# Architecture

## Scope

This repository includes the implemented CloudOps RAG pipeline through Phase 17: corpus ingestion, cleaning, character chunking, OpenAI embedding, Chroma retrieval, retrieval evaluation, threshold fallback, FastAPI service, runtime document ingestion, Evaluation/Runtime collection separation, Docker packaging, and runtime persistence.

Monitoring is not implemented yet; Phase 18 has not started.

## Planned Flow

```text
data/manifests/documents.csv
  -> ingestion fetch step
  -> data/raw/
  -> cleaning step
  -> data/processed/
  -> chunking step
  -> embedding step
  -> Chroma evaluation/runtime index
  -> retrieval
  -> retrieval evaluation
  -> answer generation with sources
  -> FastAPI service
  -> Docker runtime
```

## Source Package Layout

```text
src/cloudops_rag/
  ingestion/    document manifest loading, fetching, cleaning
  chunking/     chunk creation and chunk metadata
  embedding/    embedding provider boundary
  retrieval/    vector search and retrieved result schemas
  generation/   LLM client boundary, prompts, RAG orchestration
  evaluation/   datasets, metrics, experiment runners
  api/          FastAPI application boundary
  config/       runtime and experiment configuration
```

## Data Layout

```text
data/
  manifests/    official source inventory
  raw/          fetched source documents, ignored by git except .gitkeep
  processed/    cleaned documents, ignored by git except .gitkeep
  evaluation/   seed/dev/test evaluation files
  runtime/      runtime document status, ignored by git
```

## Chroma Collections

```text
Evaluation frozen collection:
cloudops_rag_v1_embedding_openai_text_embedding_3_small

Runtime mutable collection:
cloudops_rag_runtime_openai_text_embedding_3_small
```

The API queries and runtime document ingestion use the runtime collection. The frozen evaluation collection preserves the Phase 7-13 experiment index and is not mutated by runtime ingestion.

## Design Boundaries

- `ingestion` should know how to fetch and clean official documentation.
- `chunking` should not depend on a specific vector database.
- `embedding` should expose API and local providers behind the same interface.
- `retrieval` should return scores and document metadata for evaluation.
- `evaluation` should be runnable without calling an LLM.
- `generation` should only answer from retrieved context.
- `api` should expose service behavior without owning retrieval internals.

## Evaluation First Principle

The project should be able to measure retrieval quality before answer generation is added. This keeps the portfolio story focused on backend-quality RAG engineering rather than demo-only generation.
