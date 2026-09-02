# Production Readiness

## Goal

This document separates what is already production-like in CloudOps RAG from what is still portfolio-scale engineering.

The project is a public portfolio service, not a production deployment. The intent is to show that the RAG pipeline is evaluated, observable, failure-aware, and bounded in its use of external dependencies.

## Production-ish Today

- FastAPI REST API with consistent request/response schemas.
- Source-aware RAG responses with returned document sources.
- Similarity threshold fallback for low-confidence retrieval.
- Separate evaluation and runtime Chroma collections.
- Docker runtime with Python 3.12, non-root user, health check, and bind-mounted persistence.
- Prometheus-compatible `/metrics` endpoint.
- Bounded retry/backoff for selected transient OpenAI embedding and generation failures.
- GitHub Actions CI for tests, compile/import checks, evaluation validation, retrieval regression gate, secret scan, and Docker build smoke test.
- MIT license and bilingual README for public review.

## Not Production-grade Yet

- No authentication or authorization.
- No rate limiting or abuse protection.
- No TLS termination or deployment hardening.
- No async ingestion worker or durable retry queue.
- No circuit breaker or adaptive rate-limit handling.
- No load testing or capacity testing.
- No production alerting rules, dashboards, or on-call playbook.
- No Kubernetes deployment manifests.
- No automated answer-quality regression gate.
- Corpus and evaluation datasets are intentionally small.

## Draft SLOs

These are draft targets for a future deployed service, not measured production guarantees.

| Area | Draft SLO |
|---|---|
| Health endpoint availability | `/health` returns 200 for 99.9% of checks |
| Query availability | `/query` returns a non-5xx response for 99% of valid requests |
| Query latency | p95 under 8s for accepted in-scope queries |
| Fallback latency | p95 under 2s when generation is skipped |
| Ingestion reliability | 99% of valid supported HTML ingestion requests complete or return a bounded error |
| Source coverage guardrail | CI keeps frozen retrieval above the committed regression gates |

## Latency Budget

Approximate synchronous query budget:

| Stage | Budget |
|---|---:|
| Request validation | 50 ms |
| Query embedding | 1,500 ms typical, 30s timeout |
| Chroma retrieval | 500 ms typical |
| Threshold decision | 10 ms |
| Generation when accepted | 5,000 ms typical, 45s timeout |
| Response serialization | 50 ms |

Timeouts are intentionally treated as final failures, not retryable events. This prevents one request from multiplying worst-case latency by retry count.

## Cost Budget

The primary external cost drivers are:

- OpenAI query embeddings for each `/query`.
- OpenAI document embeddings for runtime ingestion.
- OpenAI generation for accepted queries only.

Fallback is a cost-control path: when the top-1 Chroma L2 distance is above the threshold, the service returns a fallback response and skips LLM generation.

## Dependency Failure Policy

OpenAI failures are separated from retrieval fallback:

- Fallback is a successful low-confidence retrieval response.
- OpenAI timeout is an error path and maps to `504 external_dependency_timeout`.
- Non-timeout OpenAI dependency failure maps to `503 external_dependency_unavailable`.
- Retryable OpenAI failures use bounded application-level retry: rate limit / HTTP 429, connection failure, and selected 5xx server failures.
- OpenAI SDK retries are disabled with `max_retries=0`, so the service-level policy is the authoritative retry layer.
- Permanent 4xx failures, unknown exceptions, application errors, and timeouts are not retried.

## Release Gate

Any future retriever, model, chunking, threshold, or prompt change should pass:

- unit/API tests
- compile/import check
- evaluation dataset validation
- retrieval regression gate
- secret and personal-path scans
- Docker build and health smoke test

See [Rollout Policy](ROLLOUT_POLICY.md) for the recommended rollout sequence.
