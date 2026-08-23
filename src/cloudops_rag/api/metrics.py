"""Prometheus metrics for the CloudOps RAG API."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


HTTP_REQUESTS_TOTAL = Counter(
    "cloudops_rag_http_requests_total",
    "HTTP requests handled by the CloudOps RAG API.",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "cloudops_rag_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
)

QUERY_REQUESTS_TOTAL = Counter(
    "cloudops_rag_query_requests_total",
    "RAG query requests by bounded result type.",
    ["result"],
)
QUERY_DURATION_SECONDS = Histogram(
    "cloudops_rag_query_duration_seconds",
    "End-to-end RAG query latency in seconds.",
)
RETRIEVAL_DURATION_SECONDS = Histogram(
    "cloudops_rag_retrieval_duration_seconds",
    "Vector retrieval latency in seconds.",
)
EMBEDDING_DURATION_SECONDS = Histogram(
    "cloudops_rag_embedding_duration_seconds",
    "Query embedding latency in seconds.",
)
GENERATION_DURATION_SECONDS = Histogram(
    "cloudops_rag_generation_duration_seconds",
    "LLM answer generation latency in seconds.",
)
FALLBACK_TOTAL = Counter(
    "cloudops_rag_fallback_total",
    "RAG queries rejected by threshold fallback.",
)

INGESTION_REQUESTS_TOTAL = Counter(
    "cloudops_rag_ingestion_requests_total",
    "Runtime document ingestion requests by bounded result type.",
    ["result"],
)
INGESTION_DURATION_SECONDS = Histogram(
    "cloudops_rag_ingestion_duration_seconds",
    "Runtime document ingestion latency in seconds.",
)
INGESTION_FAILURES_TOTAL = Counter(
    "cloudops_rag_ingestion_failures_total",
    "Runtime document ingestion failures by bounded reason.",
    ["reason"],
)
OPENAI_FAILURES_TOTAL = Counter(
    "cloudops_rag_openai_failures_total",
    "OpenAI dependency failures by operation.",
    ["operation"],
)


def render_metrics() -> bytes:
    return generate_latest()
