#!/usr/bin/env python3
"""Benchmark synchronous runtime document ingestion."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.api.dependencies import build_api_state


DOCUMENTS = [
    {
        "source_url": "https://kubernetes.io/docs/tasks/debug/debug-cluster/",
        "title": "Debugging Kubernetes Nodes",
        "provider": "kubernetes",
        "category": "runtime_benchmark_small",
    },
    {
        "source_url": "https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/",
        "title": "Debugging DNS Resolution",
        "provider": "kubernetes",
        "category": "runtime_benchmark_medium",
    },
    {
        "source_url": "https://docs.aws.amazon.com/eks/latest/userguide/troubleshooting.html",
        "title": "Troubleshooting Amazon EKS",
        "provider": "aws",
        "category": "runtime_benchmark_large",
    },
]


FIELDS = [
    "document_id",
    "source_url",
    "processed_chars",
    "chunk_count",
    "fetch_ms",
    "parse_ms",
    "chunk_ms",
    "embedding_ms",
    "index_ms",
    "total_ms",
    "status",
    "duplicate",
]


def main() -> int:
    state = build_api_state()
    rows = []
    for document in DOCUMENTS:
        result = state.ingestion_service.ingest(**document)
        record = result.record
        rows.append(
            {
                "document_id": record.doc_id,
                "source_url": record.source_url,
                "processed_chars": record.processed_chars or "",
                "chunk_count": record.chunk_count or "",
                "fetch_ms": record.timings_ms.get("fetch_ms", ""),
                "parse_ms": record.timings_ms.get("parse_ms", ""),
                "chunk_ms": record.timings_ms.get("chunk_ms", ""),
                "embedding_ms": record.timings_ms.get("embedding_ms", ""),
                "index_ms": record.timings_ms.get("index_ms", ""),
                "total_ms": record.timings_ms.get("total_ms", ""),
                "status": record.status,
                "duplicate": result.duplicate,
            }
        )

    output_path = PROJECT_ROOT / "results" / "ingestion" / "ingestion_benchmark.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {output_path}")
    return 0 if all(row["status"] == "completed" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
