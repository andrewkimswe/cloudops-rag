#!/usr/bin/env python3
"""Run Phase 7 baseline retrieval evaluation on the development set only."""

from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.evaluation.metrics import (
    hit_at_k,
    mean,
    multi_all_hit_at_k,
    multi_any_hit_at_k,
    reciprocal_rank,
)
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore


DEV_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_dev.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "baseline"
BASELINE_TOP_K = 3
EVALUATION_DEPTH = 10

PER_QUESTION_FIELDS = [
    "id",
    "question",
    "ground_truth_type",
    "question_type",
    "expected_document_1",
    "expected_document_2",
    "retrieved_rank_1_doc_id",
    "retrieved_rank_2_doc_id",
    "retrieved_rank_3_doc_id",
    "retrieved_rank_1_score",
    "retrieved_rank_2_score",
    "retrieved_rank_3_score",
    "hit_at_1",
    "hit_at_3",
    "any_hit_at_1",
    "any_hit_at_3",
    "all_hit_at_3",
    "reciprocal_rank",
    "retrieval_latency_ms",
]


def read_dev_rows() -> list[dict[str, str]]:
    with DEV_EVALUATION_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def expected_docs(row: dict[str, str]) -> list[str]:
    return [
        doc
        for doc in [row["expected_document_1"].strip(), row["expected_document_2"].strip()]
        if doc and doc != "NONE"
    ]


def provider_for_row(row: dict[str, str], provider_by_doc_id: dict[str, str]) -> str:
    docs = expected_docs(row)
    if not docs:
        return "out_of_scope"
    providers = {provider_by_doc_id[doc] for doc in docs}
    if len(providers) == 1:
        return next(iter(providers))
    return "mixed"


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * percentile_value))
    return sorted_values[index]


def latency_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    values = [float(row["retrieval_latency_ms"]) for row in rows]
    if not values:
        return {"mean_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0}
    return {
        "mean_ms": mean(values),
        "median_ms": statistics.median(values),
        "p95_ms": percentile(values, 0.95),
    }


def accuracy_summary(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        return {"count": 0, "hit_rate_at_1": 0.0, "hit_rate_at_3": 0.0, "mrr": 0.0}
    return {
        "count": len(rows),
        "hit_rate_at_1": mean([float(row["hit_at_1"]) for row in rows]),
        "hit_rate_at_3": mean([float(row["hit_at_3"]) for row in rows]),
        "mrr": mean([float(row["reciprocal_rank"]) for row in rows]),
    }


def multi_summary(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        return {
            "count": 0,
            "any_hit_rate_at_1": 0.0,
            "any_hit_rate_at_3": 0.0,
            "all_hit_rate_at_3": 0.0,
            "mrr": 0.0,
        }
    return {
        "count": len(rows),
        "any_hit_rate_at_1": mean([float(row["any_hit_at_1"]) for row in rows]),
        "any_hit_rate_at_3": mean([float(row["any_hit_at_3"]) for row in rows]),
        "all_hit_rate_at_3": mean([float(row["all_hit_at_3"]) for row in rows]),
        "mrr": mean([float(row["reciprocal_rank"]) for row in rows]),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    settings = Settings.from_env()
    manifest = load_manifest(settings.manifest_path)
    provider_by_doc_id = {doc.doc_id: doc.provider for doc in manifest}

    rows = read_dev_rows()
    embedder = OpenAIEmbedder(model=settings.embedding_model, api_key=settings.openai_api_key)
    store = ChromaVectorStore(settings.chroma_persist_dir, settings.chroma_collection)

    evaluated_rows: list[dict[str, Any]] = []
    out_of_scope_rows: list[dict[str, Any]] = []

    for row in rows:
        started = time.perf_counter()
        retrieved = store.retrieve(row["question"], embedder, top_k=EVALUATION_DEPTH)
        latency_ms = (time.perf_counter() - started) * 1000

        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved]
        expected = set(expected_docs(row))
        is_out_of_scope = row["ground_truth_type"] == "out_of_scope"

        top3 = retrieved[:BASELINE_TOP_K]
        result: dict[str, Any] = {
            "id": row["id"],
            "question": row["question"],
            "ground_truth_type": row["ground_truth_type"],
            "question_type": row["question_type"],
            "expected_document_1": row["expected_document_1"],
            "expected_document_2": row["expected_document_2"],
            "retrieved_rank_1_doc_id": top3[0].doc_id if len(top3) > 0 else "",
            "retrieved_rank_2_doc_id": top3[1].doc_id if len(top3) > 1 else "",
            "retrieved_rank_3_doc_id": top3[2].doc_id if len(top3) > 2 else "",
            "retrieved_rank_1_score": top3[0].score if len(top3) > 0 else "",
            "retrieved_rank_2_score": top3[1].score if len(top3) > 1 else "",
            "retrieved_rank_3_score": top3[2].score if len(top3) > 2 else "",
            "retrieval_latency_ms": round(latency_ms, 3),
        }

        if is_out_of_scope:
            result.update(
                {
                    "hit_at_1": "",
                    "hit_at_3": "",
                    "any_hit_at_1": "",
                    "any_hit_at_3": "",
                    "all_hit_at_3": "",
                    "reciprocal_rank": "",
                }
            )
            out_of_scope_rows.append(result)
        else:
            result.update(
                {
                    "hit_at_1": int(hit_at_k(expected, retrieved_doc_ids, 1)),
                    "hit_at_3": int(hit_at_k(expected, retrieved_doc_ids, BASELINE_TOP_K)),
                    "any_hit_at_1": int(multi_any_hit_at_k(expected, retrieved_doc_ids, 1)),
                    "any_hit_at_3": int(multi_any_hit_at_k(expected, retrieved_doc_ids, BASELINE_TOP_K)),
                    "all_hit_at_3": int(multi_all_hit_at_k(expected, retrieved_doc_ids, BASELINE_TOP_K)),
                    "reciprocal_rank": reciprocal_rank(expected, retrieved_doc_ids),
                }
            )
        evaluated_rows.append(result)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(RESULT_DIR / "baseline_per_question.csv", evaluated_rows, PER_QUESTION_FIELDS)
    write_csv(RESULT_DIR / "baseline_out_of_scope.csv", out_of_scope_rows, PER_QUESTION_FIELDS)

    in_scope = [row for row in evaluated_rows if row["ground_truth_type"] != "out_of_scope"]
    single_rows = [row for row in in_scope if row["ground_truth_type"] == "single"]
    multi_rows = [row for row in in_scope if row["ground_truth_type"] == "multi"]

    by_question_type_rows = []
    for question_type in sorted({row["question_type"] for row in in_scope}):
        scoped = [row for row in in_scope if row["question_type"] == question_type]
        summary = accuracy_summary(scoped)
        by_question_type_rows.append({"question_type": question_type, **summary})
    write_csv(
        RESULT_DIR / "baseline_by_question_type.csv",
        by_question_type_rows,
        ["question_type", "count", "hit_rate_at_1", "hit_rate_at_3", "mrr"],
    )

    by_provider_rows = []
    for provider in ["kubernetes", "aws", "mixed"]:
        scoped = [
            row
            for row in in_scope
            if provider_for_row(row, provider_by_doc_id) == provider
        ]
        if scoped:
            summary = accuracy_summary(scoped)
            by_provider_rows.append({"provider": provider, **summary})
    write_csv(
        RESULT_DIR / "baseline_by_provider.csv",
        by_provider_rows,
        ["provider", "count", "hit_rate_at_1", "hit_rate_at_3", "mrr"],
    )

    out_scores = [
        float(row["retrieved_rank_1_score"])
        for row in out_of_scope_rows
        if row["retrieved_rank_1_score"] != ""
    ]
    summary = {
        "baseline_config": {
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "chunk_unit": "character",
            "embedding_model": settings.embedding_model,
            "vector_db": "Chroma",
            "chroma_collection": settings.chroma_collection,
            "retrieval_top_k": BASELINE_TOP_K,
            "evaluation_depth": EVALUATION_DEPTH,
            "evaluation_dataset": str(DEV_EVALUATION_PATH.relative_to(PROJECT_ROOT)),
            "held_out_test_used": False,
        },
        "counts": {
            "dev_total": len(evaluated_rows),
            "in_scope": len(in_scope),
            "out_of_scope": len(out_of_scope_rows),
            "single": len(single_rows),
            "multi": len(multi_rows),
            "question_type": dict(Counter(row["question_type"] for row in evaluated_rows)),
            "provider": dict(
                Counter(provider_for_row(row, provider_by_doc_id) for row in evaluated_rows)
            ),
        },
        "overall_in_scope": accuracy_summary(in_scope),
        "single_document": accuracy_summary(single_rows),
        "multi_document": multi_summary(multi_rows),
        "by_question_type": by_question_type_rows,
        "by_provider": by_provider_rows,
        "latency": latency_summary(evaluated_rows),
        "out_of_scope": {
            "count": len(out_of_scope_rows),
            "top_distance_mean": mean(out_scores),
            "top_distance_median": statistics.median(out_scores) if out_scores else 0.0,
            "top_distance_min": min(out_scores) if out_scores else 0.0,
            "top_distance_max": max(out_scores) if out_scores else 0.0,
        },
    }
    (RESULT_DIR / "baseline_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
