# Failure Mode Matrix

## Goal

This document summarizes known CloudOps RAG v1 failure modes, how they are detected today, the current system behavior, and the remaining risk. It is an operational review document, not a claim that the service is production-grade.

## Matrix

| Failure mode | Detection signal | Current behavior | Current mitigation | Remaining risk |
|---|---|---|---|---|
| Low-confidence retrieval for out-of-scope query | Top-1 Chroma L2 distance above `1.042478`; fallback metrics increase | Return fallback response with `fallback=true`, no sources, and skip generation | Similarity threshold selected on Dev and validated once on Held-out OOS | OOS sample is tiny; threshold may not reject high-confidence semantic mismatch |
| High-confidence semantic misretrieval | Human review, low answer correctness/source support despite retrieved context | Request may be accepted and generation may use the wrong evidence | Source-aware answer payload makes the supporting docs inspectable | Threshold does not solve this because distance can be low for the wrong concept |
| Missing second evidence document | Multi All-Hit@k below Any-Hit@k; answer review shows incomplete evidence | Answer may cover one relevant document but miss required supporting context | Multi Any/All metrics, failure analysis, diversification candidate experiment | Multi-document completeness remains weak, especially when the missing doc is absent or too low in raw candidates |
| Duplicate chunks occupy Top-k slots | Low unique doc count, high duplicate ratio, max same-document occupancy | Final context may over-represent one document | Measured document diversity; cap=2 tested as a post-hoc candidate | cap=2 improves diversity but did not improve Hit@k/MRR on the small untouched follow-up set |
| ConfigMap/Secrets confusion | Repeated low correctness/source support on ConfigMap vs Secret questions | Answers can be faithful to retrieved Secret context while failing the actual ConfigMap question | Document-level labels, answer-quality diagnostics, human review | Similar concepts remain difficult for dense retrieval alone |
| OpenAI embedding timeout | Timeout exception; `external_dependency_timeout`; OpenAI failure metrics | Return `504 external_dependency_timeout` | 30s embedding timeout; bounded retry/backoff for selected transient failures | No circuit breaker, adaptive rate-limit handling, or async retry queue |
| OpenAI generation timeout | Timeout exception; `external_dependency_timeout`; OpenAI failure metrics | Return `504 external_dependency_timeout` | 45s generation timeout; fallback path skips generation when retrieval confidence is low | Accepted requests still depend on synchronous generation availability |
| OpenAI transient rate limit or 5xx | Retry metrics and final OpenAI failure metrics | Retry bounded transient failures; return dependency error if exhausted | SDK retries disabled; application retry policy is explicit and bounded | No global traffic shaping or queue-based smoothing |
| Runtime ingestion fetch failure | `/documents` returns `fetch_failed`; ingestion failure metrics | Store failed status record and return standard error | Status endpoint exposes failed state; error code is bounded | No async retry queue or operator retry workflow |
| Duplicate runtime document ingestion | Existing URL-derived stable document ID | Return existing completed record without appending duplicate chunks | Stable URL ID and collection separation | URL canonicalization may still miss semantically identical pages |
| Evaluation regression | CI regression gate below frozen thresholds | CI fails before merge | Committed baseline JSON plus regression gate script | Gate covers retrieval metrics, not answer-quality regression |
| Secret or local path exposure | CI/local secret and personal path scan | Fail verification when patterns are found | `.env` ignored; scans avoid printing secret values | Regex scans are necessary but not a full security audit |

## Operating Interpretation

Fallback is a controlled successful response for weak retrieval confidence. OpenAI timeout, OpenAI dependency failure, and ingestion failure are error paths. These should be monitored and discussed separately because they imply different operator actions.

Multi-document completeness remains the main retrieval weakness. The system often finds at least one relevant document, but does not reliably gather all required evidence documents for questions that need comparison or cross-service diagnosis.

## Related Documents

- [Evaluation Summary](EVALUATION_SUMMARY.md)
- [Limitations](LIMITATIONS.md)
- [Retrieval Diversification](RETRIEVAL_DIVERSIFICATION.md)
- [Monitoring](MONITORING.md)
- [Production Readiness](PRODUCTION_READINESS.md)
- [Runbook](RUNBOOK.md)
