#!/usr/bin/env python3
"""Run a small mock load smoke test against the FastAPI query path.

This smoke test does not call OpenAI or Chroma. It validates API behavior under
small concurrent request volume using an in-process fake RAG service.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from fastapi.testclient import TestClient
except ImportError as exc:  # pragma: no cover
    raise SystemExit("fastapi test dependencies are required for mock load smoke") from exc

from cloudops_rag.api.app import create_app
from cloudops_rag.retrieval.schemas import RagResult, RetrievedChunk, Source


@dataclass
class FakeCollection:
    indexed_count: int = 483

    def count(self) -> int:
        return self.indexed_count


@dataclass
class FakeVectorStore:
    collection_name: str = "mock_load_smoke_collection"
    collection: FakeCollection = field(default_factory=FakeCollection)


class FakeRagService:
    top_k = 5

    def __init__(self, latency_ms: float = 5.0):
        self.latency_ms = latency_ms
        self.calls = 0
        self.lock = Lock()

    def query(self, question: str) -> RagResult:
        with self.lock:
            self.calls += 1
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000)
        if "timeout" in question:
            raise TimeoutError("mock dependency timeout")
        if "error" in question:
            raise RuntimeError("mock dependency error")
        if "unsupported" in question:
            return RagResult(
                question=question,
                answer="I couldn't find sufficient support for this question in the indexed documents.",
                sources=[],
                retrieved_chunks=[make_chunk(score=1.5)],
                fallback=True,
                retrieval_distance=1.5,
                distance_threshold=1.042478,
            )
        return RagResult(
            question=question,
            answer="Use kubectl describe pod and inspect scheduling events.",
            sources=[
                Source(
                    doc_id="k8s_debug_pods",
                    title="Debug Pods",
                    source_url="https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
                    rank=1,
                )
            ],
            retrieved_chunks=[make_chunk(score=0.7)],
            fallback=False,
            retrieval_distance=0.7,
            distance_threshold=1.042478,
        )


def make_chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        doc_id="k8s_debug_pods",
        title="Debug Pods",
        source_url="https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
        provider="kubernetes",
        category="pod_troubleshooting",
        chunk_id="k8s_debug_pods::0000",
        chunk="debug pod content",
        score=score,
    )


def create_mock_client(latency_ms: float = 5.0) -> tuple[TestClient, FakeRagService]:
    service = FakeRagService(latency_ms=latency_ms)
    app = create_app()
    app.state.api_state = type(
        "MockApiState",
        (),
        {
            "vector_store": FakeVectorStore(),
            "rag_service": service,
            "ingestion_service": None,
            "documents": {},
        },
    )()
    return TestClient(app), service


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * p))
    return ordered[index]


def run_smoke(requests: int, concurrency: int, latency_ms: float) -> dict[str, Any]:
    client, service = create_mock_client(latency_ms=latency_ms)
    questions = []
    for index in range(requests):
        if index % 10 == 8:
            questions.append("unsupported laptop buying advice")
        elif index % 10 == 9:
            questions.append("timeout while embedding")
        else:
            questions.append(f"Why is my Pod Pending? request {index}")

    def call(question: str) -> dict[str, Any]:
        started = time.perf_counter()
        response = client.post("/query", json={"question": question})
        elapsed_ms = (time.perf_counter() - started) * 1000
        body = response.json()
        return {
            "status_code": response.status_code,
            "latency_ms": elapsed_ms,
            "fallback": body.get("fallback", False),
            "error_code": body.get("error", {}).get("code"),
        }

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(call, question) for question in questions]
        for future in as_completed(futures):
            results.append(future.result())

    latencies = [result["latency_ms"] for result in results]
    status_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for result in results:
        status_counts[str(result["status_code"])] = status_counts.get(str(result["status_code"]), 0) + 1
        if result["error_code"]:
            error_counts[result["error_code"]] = error_counts.get(result["error_code"], 0) + 1

    return {
        "requests": requests,
        "concurrency": concurrency,
        "mock_service_calls": service.calls,
        "status_counts": status_counts,
        "fallback_count": sum(1 for result in results if result["fallback"]),
        "error_counts": error_counts,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "p50": round(statistics.median(latencies), 3) if latencies else 0.0,
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "openai_calls": 0,
        "chroma_calls": 0,
    }


def main() -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description="Run mock load smoke against the FastAPI query path.")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--latency-ms", type=float, default=5.0)
    args = parser.parse_args()

    if args.requests <= 0:
        raise SystemExit("--requests must be positive")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be positive")

    summary = run_smoke(args.requests, args.concurrency, args.latency_ms)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if summary["status_counts"].get("200", 0) == 0:
        return 1
    if summary["error_counts"].get("external_dependency_timeout", 0) == 0:
        return 1
    if summary["fallback_count"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
