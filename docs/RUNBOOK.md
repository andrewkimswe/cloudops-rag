# Runbook

## Goal

This runbook gives a lightweight operator workflow for CloudOps RAG v1. It assumes the current portfolio-scale FastAPI service, not a hardened production deployment.

## Quick Checks

| Check | Command | Expected result |
|---|---|---|
| API health | `curl http://localhost:8000/health` | `status` is `ok` |
| Metrics endpoint | `curl http://localhost:8000/metrics` | Prometheus text output is returned |
| Unit and regression tests | `work/python312/bin/python3.12 -m pytest` | all tests pass |
| Retrieval regression gate | `work/python312/bin/python3.12 scripts/check_eval_regression.py` | exits 0 |
| Mock API load smoke | `work/python312/bin/python3.12 scripts/mock_load_smoke.py` | exits 0 and prints bounded latency/error summary |

## Query Incident Triage

### Fallback Rate Increase

Signal:

- `cloudops_rag_fallback_total` increases faster than query traffic.
- More `/query` responses return `fallback=true`.

Interpretation:

- User questions may be outside the AWS/Kubernetes corpus.
- The corpus may be missing required documents.
- The threshold may be too strict for the current query mix.

Actions:

1. Sample fallback questions without logging secrets or sensitive user data.
2. Check whether questions are genuinely out of scope.
3. If in scope, map missing evidence to `doc_id` candidates in `data/manifests/documents.csv`.
4. Add or refresh corpus documents only through the documented ingestion path.
5. Re-run retrieval evaluation before changing threshold or retriever configuration.

### OpenAI Timeout Increase

Signal:

- `cloudops_rag_openai_failures_total{operation="embedding"}` or `{operation="generation"}` increases.
- API returns `504 external_dependency_timeout`.

Interpretation:

- This is an external dependency error path, not retrieval fallback.
- Current timeouts are 30s for embedding and 45s for generation.

Actions:

1. Confirm whether failures are embedding or generation.
2. Check retry metrics for transient pressure.
3. Avoid increasing timeout as the first response because it can worsen p95 latency.
4. If failures persist, consider circuit breaker or queue-based handling in a future version.

### OpenAI 503 / Dependency Failure Increase

Signal:

- API returns `503 external_dependency_unavailable`.
- Retry metrics increase and final failure metrics also increase.

Actions:

1. Separate rate-limit, connection, and server-error patterns.
2. Confirm bounded retry policy is not multiplying request latency unexpectedly.
3. Treat persistent failure as degraded service rather than fallback.
4. Future mitigation candidates: circuit breaker, adaptive rate limits, or async retry queue.

### Retrieval Regression In CI

Signal:

- GitHub Actions fails retrieval regression gate.
- `scripts/check_eval_regression.py` exits non-zero.

Actions:

1. Identify whether the change touched chunking, embedding model, retrieval depth, threshold, corpus, or evaluation labels.
2. Compare per-question failures before changing thresholds.
3. Do not use Held-out Test as a tuning set.
4. Update the frozen baseline only after an intentional evaluation decision is documented.

### Multi-document Completeness Failure

Signal:

- Multi Any-Hit remains high while Multi All-Hit remains low.
- Answers cite one useful source but miss the second required evidence document.

Actions:

1. Inspect raw candidate depth to see whether the missing document appears at all.
2. If present but displaced, test document diversification or MMR candidates.
3. If absent, focus on candidate generation: query rewriting, decomposition, hybrid search, or metadata-aware retrieval.
4. Validate candidates on untouched evaluation data before runtime adoption.

### Runtime Ingestion Failure

Signal:

- `/documents` returns a bounded error such as `fetch_failed`, `invalid_content`, `embedding_failed`, or `indexing_failed`.
- `cloudops_rag_ingestion_failures_total{reason=...}` increases.

Actions:

1. Check `/documents/{doc_id}/status` for the stored failure record.
2. Verify the URL is official and fetchable.
3. Confirm parsing produced usable text before embedding/indexing.
4. Re-run ingestion after fixing the source issue.
5. Re-run retrieval evaluation if the corpus changes materially.

## Deployment Notes

- Fallback is a normal response path and should not page by itself.
- OpenAI dependency failures are error paths and should be tracked separately.
- The current service has no auth, rate limit, circuit breaker, async ingestion, async retry queue, or large-scale load validation.
- Do not log API keys, raw credentials, full question text, source URLs with secrets, or local filesystem paths.

## Future Runbook Additions

- Alert thresholds once real traffic exists.
- Dashboard links once Prometheus/Grafana are deployed.
- Circuit breaker trip and recovery procedure if implemented.
- Async ingestion retry and dead-letter handling if implemented.
