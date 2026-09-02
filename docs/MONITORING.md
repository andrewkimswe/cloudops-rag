# Monitoring

## Goal

Phase 18 adds Prometheus-compatible metrics to the FastAPI RAG service without changing the frozen retrieval configuration, threshold, answer generation behavior, or evaluation results.

The metrics endpoint is intentionally lightweight:

```text
GET /metrics
```

It does not call OpenAI, Chroma, or the RAG pipeline.

## Metric Prefix

All project-specific metrics use the prefix:

```text
cloudops_rag_
```

The endpoint may also expose default Python process metrics from `prometheus-client`.

## Exposed Metrics

HTTP metrics:

- `cloudops_rag_http_requests_total{method,endpoint,status_code}`
- `cloudops_rag_http_request_duration_seconds{method,endpoint}`

Query metrics:

- `cloudops_rag_query_requests_total{result}`
- `cloudops_rag_query_duration_seconds`
- `cloudops_rag_embedding_duration_seconds`
- `cloudops_rag_retrieval_duration_seconds`
- `cloudops_rag_generation_duration_seconds`
- `cloudops_rag_fallback_total`
- `cloudops_rag_openai_failures_total{operation}`
- `cloudops_rag_external_retries_total{operation,reason}`

Ingestion metrics:

- `cloudops_rag_ingestion_requests_total{result}`
- `cloudops_rag_ingestion_duration_seconds`
- `cloudops_rag_ingestion_failures_total{reason}`

## Label Policy

Labels are intentionally bounded to avoid high-cardinality Prometheus series.

Allowed labels include:

- HTTP method
- route template endpoint, such as `/documents/{doc_id}/status`
- HTTP status code
- query result: `answered`, `fallback`, `error`
- ingestion result: `completed`, `duplicate`, `failed`
- ingestion failure reason from a bounded error-code set such as `fetch_failed`, `invalid_content`, `embedding_failed`, or `indexing_failed`
- OpenAI operation: `embedding`, `generation`
- external retry reason: `rate_limit`, `connection_error`, `server_error`

The service does not use question text, answer text, `doc_id`, `chunk_id`, source URL, document URL, exception message, or user input as metric labels.


## Retry Metric Semantics

`cloudops_rag_external_retries_total{operation,reason}` increments when an additional retry attempt starts. It does not increment for the initial attempt.

Allowed values are intentionally bounded:

- `operation`: `embedding`, `generation`
- `reason`: `rate_limit`, `connection_error`, `server_error`

If a transient OpenAI failure succeeds after retry, this retry metric increments but `cloudops_rag_openai_failures_total{operation}` does not increment because that metric tracks final operation failures. Timeout, permanent 4xx, unknown exception, and application errors are not retried.

## Query Timing Semantics

`cloudops_rag_query_duration_seconds` measures the full query lifecycle:

```text
embedding -> retrieval -> threshold decision -> generation when accepted
```

If threshold fallback rejects the query, generation is skipped and `cloudops_rag_generation_duration_seconds` is not observed for that request.

## Monitoring Budget

The current metric set is intentionally small. Each metric should answer a concrete operating question without exposing high-cardinality user content.

| Signal | Metric | Why it matters |
|---|---|---|
| Query volume and result mix | `cloudops_rag_query_requests_total{result}` | Shows answered, fallback, and error balance |
| End-to-end query latency | `cloudops_rag_query_duration_seconds` | Tracks user-visible synchronous request cost |
| Embedding latency | `cloudops_rag_embedding_duration_seconds` | Isolates query embedding as an external dependency cost |
| Retrieval latency | `cloudops_rag_retrieval_duration_seconds` | Separates Chroma/vector search latency from OpenAI latency |
| Generation latency | `cloudops_rag_generation_duration_seconds` | Tracks accepted-query LLM generation cost |
| Fallback count/rate | `cloudops_rag_fallback_total` | Detects corpus mismatch, threshold drift, or unsupported query mix |
| OpenAI final failures | `cloudops_rag_openai_failures_total{operation}` | Tracks dependency failures that remain after retry policy |
| OpenAI retry attempts | `cloudops_rag_external_retries_total{operation,reason}` | Shows transient dependency pressure before it becomes final failure |
| Ingestion success/failure | `cloudops_rag_ingestion_requests_total{result}` and `cloudops_rag_ingestion_failures_total{reason}` | Tracks runtime corpus update health |

Operational ratios can be derived outside the app:

- fallback rate = fallback queries / total queries
- OpenAI error rate = OpenAI final failures / query or ingestion volume
- retry pressure = retry attempts / OpenAI operations
- ingestion failure rate = failed ingestion requests / ingestion requests

The service intentionally avoids labels for question text, answer text, document URL, `doc_id`, `chunk_id`, raw exception messages, API keys, or local paths.

## Docker

The Docker image exposes the same endpoint:

```bash
curl http://localhost:8000/metrics
```

The Dockerfile health check remains pointed at:

```text
GET /health
```

## Current Scope

Phase 18 adds application metrics only. It does not add a Prometheus server, Grafana dashboard, OpenTelemetry tracing, alert rules, authentication, or Kubernetes deployment manifests.

The post-hoc retrieval diversification result, including cap=2, remains a candidate experiment and is not promoted to the production/frozen retriever.
