# Document Ingestion

## 1. Goal

Phase 16 connects `POST /documents` to a real runtime ingestion lifecycle:

```text
register -> pending -> processing -> fetch -> parse/clean -> chunk -> embed -> Chroma index -> completed
```

Failures are recorded as `failed` with a safe error code/message.

## 2. Workflow

The API calls `DocumentIngestionService`, which reuses the existing fetch, HTML cleaning, character chunking, OpenAI embedding, and Chroma indexing code.

```text
FastAPI route
  -> DocumentIngestionService
  -> fetch_html
  -> html_to_text
  -> chunk_documents
  -> OpenAI text-embedding-3-small
  -> runtime Chroma collection
  -> JSON status registry
```

The implementation is intentionally synchronous for the first runtime baseline.

## 3. Document States

- `pending`: registration was accepted and persisted.
- `processing`: fetch/parse/chunk/embed/index work is running.
- `completed`: chunks were successfully indexed.
- `failed`: ingestion failed; a safe `error_code` and `message` are available.

Status records include `doc_id`, `source_url`, `created_at`, `updated_at`, optional metadata, `processed_chars`, `chunk_count`, and timing fields when available.

## 4. Duplicate Policy

`doc_id` is stable: `registered_<sha1(source_url)[:12]>`.

If the same `source_url` already has a `completed` status, `POST /documents` returns the existing completed record with `duplicate=true`. The document is not fetched, embedded, or indexed again. This prevents duplicate chunks from accumulating.

Failed documents with the same URL can be retried because the same stable `doc_id` is reused and existing chunks for that `doc_id` are deleted before indexing.

## 5. Indexing Strategy

Phase 13 evaluation used the frozen collection:

```text
cloudops_rag_v1_embedding_openai_text_embedding_3_small
```

Phase 16 runtime ingestion uses a mutable service collection:

```text
cloudops_rag_runtime_openai_text_embedding_3_small
```

On API startup, if the runtime collection is empty, it is seeded from the frozen evaluation collection. New API-ingested documents are added only to the runtime collection.

## 6. Evaluation Corpus vs Runtime Corpus

Evaluation Corpus:

- 20 official AWS/Kubernetes documents
- Used for Phase 7-13 experiments
- Historical results remain frozen and reproducible

Runtime Corpus:

- Starts from the evaluation corpus when seeded
- Can grow through `POST /documents`
- May have a different score distribution after new documents are added

New runtime ingestion must not overwrite Phase 7-13 CSV/JSON results.

## 7. Synchronous Baseline

The first Phase 16 implementation is synchronous:

```text
POST /documents -> completed or failed response
```

This keeps the architecture explainable and avoids adding queues, workers, Redis, or Celery before measured latency shows they are necessary.

## 8. Ingestion Benchmark

Benchmark results are stored at:

```text
results/ingestion/ingestion_benchmark.csv
```

Columns:

```text
document_id, source_url, processed_chars, chunk_count,
fetch_ms, parse_ms, chunk_ms, embedding_ms, index_ms, total_ms,
status, duplicate
```

Phase 16 measured three representative official documents:

| document_id | processed_chars | chunk_count | fetch_ms | parse_ms | chunk_ms | embedding_ms | index_ms | total_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `registered_89c93ad58ae8` | 20,083 | 23 | 1,840.41 | 111.44 | 0.03 | 2,296.65 | 51.61 | 4,300.14 |
| `registered_051a680a02dd` | 13,359 | 15 | 1,920.97 | 99.87 | 0.03 | 473.72 | 44.12 | 2,538.71 |
| `registered_d905a95144a4` | 54,536 | 61 | 369.20 | 48.75 | 0.09 | 333.26 | 70.19 | 821.49 |

## 9. Sync vs Async Decision

The decision is based on measured runtime:

- If representative documents complete within a tolerable local HTTP request time, synchronous ingestion remains acceptable.
- If large documents are dominated by embedding latency, hit timeout risk, or need concurrent ingestion, Phase 17 can introduce a small background worker or FastAPI background task.

Async is not introduced only because it is more complex.

Phase 16 decision: keep synchronous ingestion for now. The measured documents completed in about 0.8-4.3 seconds in this local environment. That is acceptable for a portfolio/development API where ingestion is an operator action, not a high-throughput user path.

## 10. Failure Handling

Handled failure classes:

- invalid URL / unsupported scheme
- fetch failure
- fetch timeout
- unsupported non-HTML content
- parsing failure or too little parsed text
- embedding failure
- Chroma indexing failure

API responses expose safe error codes/messages, not stack traces.

## 11. Idempotency

Stable document IDs plus Chroma upsert IDs prevent same-doc chunk growth. Completed duplicate URLs return the existing record.

For retried failed documents, the service deletes existing chunks for that `doc_id` before upsert and verifies the final indexed chunk count.

## 12. Partial Failure

There is no distributed transaction across OpenAI and Chroma. The service still handles practical partial failure by deleting chunks for the document on failure and by deleting existing chunks for the same `doc_id` before indexing.

This is sufficient for the current single-process portfolio service, but production ingestion would need stronger job tracking and retry semantics.

## 13. API Contract

`POST /documents` synchronously ingests an HTML document and returns a completed record:

```json
{
  "doc_id": "registered_...",
  "status": "completed",
  "message": "Document ingestion completed.",
  "source_url": "https://...",
  "chunk_count": 12,
  "processed_chars": 10240,
  "duplicate": false,
  "timings_ms": {
    "fetch_ms": 100.0,
    "parse_ms": 20.0,
    "chunk_ms": 1.0,
    "embedding_ms": 900.0,
    "index_ms": 30.0,
    "total_ms": 1051.0
  }
}
```

`GET /documents/{id}/status` returns the persisted status record.

## 14. Current Limitations

- Status persistence is a local JSON file, not SQLite or a durable service database.
- Synchronous ingestion ties request latency to fetch and embedding latency.
- Runtime corpus expansion can change retrieval score distributions, so the development-selected threshold may require recalibration in a production deployment.
- Only HTML documents are supported.
- No authentication, rate limiting, retry queue, or concurrent ingestion control is implemented.

## 15. When Async Would Be Needed

Async/background ingestion should be considered when:

- representative large documents approach API gateway or client timeout limits
- multiple documents must be ingested concurrently
- embedding latency dominates total time
- retries/backoff need to survive process restarts
- operators need cancellable jobs or richer progress reporting
