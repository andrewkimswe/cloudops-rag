# Phase 15. REST API

## 1. Overview

Phase 15 exposed the frozen CloudOps RAG pipeline through a small FastAPI REST API.
Phase 16 adds synchronous runtime document ingestion.

The API does not change retrieval quality settings. It uses the frozen configuration selected in Phase 11 and Phase 12:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character

embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5

threshold_signal = Top-1 Chroma L2 distance
threshold = 1.042478
```

## 2. Run

Prerequisites:

- `.env` contains `OPENAI_API_KEY`
- Chroma index exists for the frozen evaluation collection `cloudops_rag_v1_embedding_openai_text_embedding_3_small`
- Runtime API queries use mutable collection `cloudops_rag_runtime_openai_text_embedding_3_small`
- project dependencies are installed from `pyproject.toml`

Run:

```bash
PYTHONPATH=src uvicorn cloudops_rag.api.app:app --reload
```

Swagger UI:

```text
http://localhost:8000/docs
```

OpenAPI JSON:

```text
http://localhost:8000/openapi.json
```

## 3. Authentication

The API currently has no external authentication layer.

This is acceptable for the local portfolio/development stage. Do not expose it publicly without adding authentication, rate limits, and deployment controls.

## 4. POST /query

Runs the frozen RAG pipeline.

Request:

```json
{
  "question": "Why is my Kubernetes Pod stuck in Pending?"
}
```

Response:

```json
{
  "question": "Why is my Kubernetes Pod stuck in Pending?",
  "answer": "...",
  "fallback": false,
  "sources": [
    {
      "doc_id": "k8s_debug_pods",
      "title": "Debug Pods",
      "source_url": "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
      "rank": 1
    }
  ],
  "debug": null
}
```

Optional debug request:

```json
{
  "question": "Why is my Kubernetes Pod stuck in Pending?",
  "debug": true
}
```

Debug mode includes Top-1 distance, threshold, retrieval top-k, and retrieved chunk metadata. The default response avoids exposing internal retrieval diagnostics.

## 5. POST /documents

Synchronously ingests one HTML document URL into the runtime Chroma collection.

Lifecycle:

```text
pending -> processing -> completed
```

If ingestion fails, the status is persisted as `failed` and the API returns a standard error response.

Request:

```json
{
  "source_url": "https://example.com/cloudops-doc",
  "title": "Example CloudOps Doc",
  "provider": "example",
  "category": "troubleshooting"
}
```

Response:

```json
{
  "doc_id": "registered_...",
  "status": "completed",
  "message": "Document ingestion completed.",
  "source_url": "https://example.com/cloudops-doc",
  "chunk_count": 8,
  "processed_chars": 7200,
  "duplicate": false,
  "timings_ms": {
    "fetch_ms": 120.0,
    "parse_ms": 30.0,
    "chunk_ms": 1.0,
    "embedding_ms": 900.0,
    "index_ms": 20.0,
    "total_ms": 1071.0
  }
}
```

Duplicate policy:

- `doc_id` is `registered_<sha1(source_url)[:12]>`
- if the same URL already completed, the existing record is returned with `duplicate=true`
- duplicate chunks are not appended

## 6. GET /documents/{id}/status

Returns the current persisted status for a runtime-ingested document. Manifest documents are still visible as registered corpus entries.

Response:

```json
{
  "doc_id": "registered_...",
  "status": "completed",
  "title": "Example CloudOps Doc",
  "source_url": "https://example.com/cloudops-doc",
  "message": "Document ingestion completed.",
  "provider": "example",
  "category": "troubleshooting",
  "created_at": "2026-08-22T00:00:00Z",
  "updated_at": "2026-08-22T00:00:02Z",
  "chunk_count": 8,
  "processed_chars": 7200,
  "error_code": null,
  "timings_ms": {
    "fetch_ms": 120.0,
    "parse_ms": 30.0,
    "chunk_ms": 1.0,
    "embedding_ms": 900.0,
    "index_ms": 20.0,
    "total_ms": 1071.0
  }
}
```

Unknown documents return `404`.

## 7. GET /health

Checks application and Chroma collection availability without calling OpenAI.

Response:

```json
{
  "status": "ok",
  "chroma_collection": "cloudops_rag_runtime_openai_text_embedding_3_small",
  "indexed_chunk_count": 483
}
```

`indexed_chunk_count` is runtime-state dependent. A seeded runtime collection starts from the frozen evaluation corpus, and API-ingested documents can increase this count.

## 8. Error Response

Errors use a consistent shape:

```json
{
  "error": {
    "code": "document_not_found",
    "message": "Document 'missing' was not found."
  }
}
```

Examples:

- `422 invalid_request`: malformed request or blank question
- `400 invalid_url`: unsupported URL format or scheme
- `400 fetch_failed`: document could not be fetched
- `400 invalid_content`: fetched content is not supported HTML
- `400 parsing_failed`: parsed document had insufficient text
- `404 document_not_found`: document status id is unknown
- `503 external_dependency_unavailable`: retrieval or generation dependency failed
- `503 external_dependency_timeout`: external dependency timed out
- `500 internal_error`: unexpected API failure

## 9. Fallback Behavior

The API reuses the Phase 12 fallback logic.

Decision rule:

```text
top_1_l2_distance <= 1.042478 -> Accept
top_1_l2_distance > 1.042478  -> Fallback
```

Accept:

- LLM is called
- answer is generated
- sources are returned

Reject:

- LLM call is skipped
- fallback answer is returned
- `sources = []`

Fallback response:

```json
{
  "question": "...",
  "answer": "I couldn't find sufficient support for this question in the indexed documents.",
  "fallback": true,
  "sources": [],
  "debug": null
}
```

## 10. Example Requests

Health:

```bash
curl http://localhost:8000/health
```

Query:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Why is my Kubernetes Pod stuck in Pending?"}'
```

Fallback query:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the best laptop to buy for running local LLMs this year?"}'
```

Register document:

```bash
curl -X POST http://localhost:8000/documents \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://example.com/cloudops-doc","title":"Example CloudOps Doc"}'
```

Document status:

```bash
curl http://localhost:8000/documents/k8s_debug_pods/status
```

## 11. Current Limitations

- The API exposes the current frozen retrieval pipeline; it does not improve retrieval quality.
- Multi-document completeness remains weak.
- ConfigMap / Secrets semantic confusion remains a known limitation.
- Duplicate chunks can still limit Top-k document diversity.
- Answer correctness, faithfulness, citation quality, and hallucination rate have not been formally evaluated.
- Document ingestion is synchronous and intentionally minimal; it is not a durable background job system.
- Docker packaging is available, but no authentication, streaming, load test, Prometheus, Kubernetes deployment, or monitoring stack is included yet.
