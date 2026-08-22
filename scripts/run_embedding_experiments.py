#!/usr/bin/env python3
"""Run Phase 9 embedding model comparison on the development set only."""

from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.chunking.chunker import chunk_documents
from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.embedding.sentence_transformer_embedder import SentenceTransformerEmbedder
from cloudops_rag.evaluation.metrics import (
    hit_at_k,
    mean,
    multi_all_hit_at_k,
    multi_any_hit_at_k,
    reciprocal_rank,
)
from cloudops_rag.ingestion.loader import load_processed_documents
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore


DEV_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_dev.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "embedding"
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128
BASELINE_TOP_K = 3
EVALUATION_DEPTH = 10
TRACKED_QUESTION_IDS = {"eval_002", "eval_007", "eval_019", "eval_027"}
TRACKED_MULTI_IDS = {"eval_021", "eval_023", "eval_024"}

EXPERIMENTS = [
    {
        "experiment_id": "openai_text_embedding_3_small",
        "embedding_model": "text-embedding-3-small",
        "embedding_type": "api",
        "collection_suffix": "openai_text_embedding_3_small",
        "dimension": 1536,
    },
    {
        "experiment_id": "local_all_minilm_l6_v2",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_type": "local",
        "collection_suffix": "local_all_minilm_l6_v2",
        "dimension": "",
    },
]

PER_QUESTION_FIELDS = [
    "experiment_id",
    "embedding_model",
    "embedding_type",
    "embedding_dimension",
    "chunk_size",
    "chunk_overlap",
    "chunk_count",
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


def create_embedder(experiment: dict[str, Any], settings: Settings):
    if experiment["embedding_type"] == "api":
        return OpenAIEmbedder(model=experiment["embedding_model"], api_key=settings.openai_api_key)
    return SentenceTransformerEmbedder(model_name=experiment["embedding_model"])


def embedding_dimension(embedder: Any, experiment: dict[str, Any]) -> int:
    if experiment["dimension"]:
        return int(experiment["dimension"])
    return int(embedder.dimension)


def evaluate_experiment(
    experiment: dict[str, Any],
    rows: list[dict[str, str]],
    settings: Settings,
    provider_by_doc_id: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    documents = load_processed_documents(settings.processed_dir)
    chunks = chunk_documents(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunk_count = len(chunks)

    model_load_started = time.perf_counter()
    embedder = create_embedder(experiment, settings)
    model_load_time_ms = (time.perf_counter() - model_load_started) * 1000
    dimension = embedding_dimension(embedder, experiment)

    collection_name = f"{settings.chroma_collection}_embedding_{experiment['collection_suffix']}"
    store = ChromaVectorStore(settings.chroma_persist_dir, collection_name)
    indexing_started = time.perf_counter()
    indexed_count = store.index_chunks(chunks, embedder, reset=True)
    indexing_time_ms = (time.perf_counter() - indexing_started) * 1000

    evaluated_rows: list[dict[str, Any]] = []
    for row in rows:
        started = time.perf_counter()
        retrieved = store.retrieve(row["question"], embedder, top_k=EVALUATION_DEPTH)
        latency_ms = (time.perf_counter() - started) * 1000

        expected = set(expected_docs(row))
        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved]
        top3 = retrieved[:BASELINE_TOP_K]
        is_out_of_scope = row["ground_truth_type"] == "out_of_scope"

        result: dict[str, Any] = {
            "experiment_id": experiment["experiment_id"],
            "embedding_model": experiment["embedding_model"],
            "embedding_type": experiment["embedding_type"],
            "embedding_dimension": dimension,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "chunk_count": chunk_count,
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

    in_scope = [row for row in evaluated_rows if row["ground_truth_type"] != "out_of_scope"]
    single_rows = [row for row in in_scope if row["ground_truth_type"] == "single"]
    multi_rows = [row for row in in_scope if row["ground_truth_type"] == "multi"]
    out_rows = [row for row in evaluated_rows if row["ground_truth_type"] == "out_of_scope"]

    provider_rows = []
    for provider in ["kubernetes", "aws", "mixed"]:
        scoped = [row for row in in_scope if provider_for_row(row, provider_by_doc_id) == provider]
        if scoped:
            provider_rows.append({"provider": provider, **accuracy_summary(scoped)})

    question_type_rows = []
    for question_type in sorted({row["question_type"] for row in in_scope}):
        scoped = [row for row in in_scope if row["question_type"] == question_type]
        question_type_rows.append({"question_type": question_type, **accuracy_summary(scoped)})

    out_scores = [float(row["retrieved_rank_1_score"]) for row in out_rows if row["retrieved_rank_1_score"] != ""]
    overall = accuracy_summary(in_scope)
    single = accuracy_summary(single_rows)
    multi = multi_summary(multi_rows)
    latency = latency_summary(evaluated_rows)
    summary = {
        "experiment_id": experiment["experiment_id"],
        "embedding_model": experiment["embedding_model"],
        "embedding_type": experiment["embedding_type"],
        "embedding_dimension": dimension,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "chunk_unit": "character",
        "chunk_count": chunk_count,
        "indexed_count": indexed_count,
        "model_load_time_ms": model_load_time_ms,
        "indexing_time_ms": indexing_time_ms,
        "vector_db": "Chroma",
        "chroma_collection": collection_name,
        "retrieval_top_k": BASELINE_TOP_K,
        "evaluation_depth": EVALUATION_DEPTH,
        "evaluation_dataset": str(DEV_EVALUATION_PATH.relative_to(PROJECT_ROOT)),
        "held_out_test_used": False,
        "overall_hit_at_1": overall["hit_rate_at_1"],
        "overall_hit_at_3": overall["hit_rate_at_3"],
        "overall_mrr": overall["mrr"],
        "single_hit_at_1": single["hit_rate_at_1"],
        "single_hit_at_3": single["hit_rate_at_3"],
        "single_mrr": single["mrr"],
        "multi_any_hit_at_3": multi["any_hit_rate_at_3"],
        "multi_all_hit_at_3": multi["all_hit_rate_at_3"],
        "multi_mrr": multi["mrr"],
        "mean_latency_ms": latency["mean_ms"],
        "median_latency_ms": latency["median_ms"],
        "p95_latency_ms": latency["p95_ms"],
        "out_of_scope_count": len(out_rows),
        "out_of_scope_top_distance_mean": mean(out_scores),
        "out_of_scope_top_distance_median": statistics.median(out_scores) if out_scores else 0.0,
        "out_of_scope_top_distance_min": min(out_scores) if out_scores else 0.0,
        "out_of_scope_top_distance_max": max(out_scores) if out_scores else 0.0,
        "api_cost_required": experiment["embedding_type"] == "api",
        "external_api_required": experiment["embedding_type"] == "api",
        "api_key_required": experiment["embedding_type"] == "api",
        "local_execution": experiment["embedding_type"] == "local",
        "offline_after_download": experiment["embedding_type"] == "local",
        "question_type_counts": dict(Counter(row["question_type"] for row in evaluated_rows)),
        "provider_counts": dict(Counter(provider_for_row(row, provider_by_doc_id) for row in evaluated_rows)),
    }
    return evaluated_rows, summary, question_type_rows, provider_rows


def main() -> int:
    settings = Settings.from_env()
    rows = read_dev_rows()
    manifest = load_manifest(settings.manifest_path)
    provider_by_doc_id = {doc.doc_id: doc.provider for doc in manifest}

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    all_per_question: list[dict[str, Any]] = []
    all_out_of_scope: list[dict[str, Any]] = []
    all_summaries: list[dict[str, Any]] = []
    all_question_type_rows: list[dict[str, Any]] = []
    all_provider_rows: list[dict[str, Any]] = []

    for experiment in EXPERIMENTS:
        print(f"Running {experiment['experiment_id']} ({experiment['embedding_model']})")
        per_question, summary, question_type_rows, provider_rows = evaluate_experiment(
            experiment, rows, settings, provider_by_doc_id
        )
        all_per_question.extend(per_question)
        all_out_of_scope.extend(row for row in per_question if row["ground_truth_type"] == "out_of_scope")
        all_summaries.append(summary)
        for row in question_type_rows:
            all_question_type_rows.append(
                {
                    "experiment_id": experiment["experiment_id"],
                    "embedding_model": experiment["embedding_model"],
                    "embedding_type": experiment["embedding_type"],
                    **row,
                }
            )
        for row in provider_rows:
            all_provider_rows.append(
                {
                    "experiment_id": experiment["experiment_id"],
                    "embedding_model": experiment["embedding_model"],
                    "embedding_type": experiment["embedding_type"],
                    **row,
                }
            )

    write_csv(RESULT_DIR / "embedding_per_question.csv", all_per_question, PER_QUESTION_FIELDS)
    write_csv(RESULT_DIR / "embedding_out_of_scope.csv", all_out_of_scope, PER_QUESTION_FIELDS)
    summary_fields = [
        "experiment_id",
        "embedding_model",
        "embedding_type",
        "embedding_dimension",
        "chunk_size",
        "chunk_overlap",
        "chunk_unit",
        "chunk_count",
        "indexed_count",
        "model_load_time_ms",
        "indexing_time_ms",
        "vector_db",
        "chroma_collection",
        "retrieval_top_k",
        "evaluation_depth",
        "evaluation_dataset",
        "held_out_test_used",
        "overall_hit_at_1",
        "overall_hit_at_3",
        "overall_mrr",
        "single_hit_at_1",
        "single_hit_at_3",
        "single_mrr",
        "multi_any_hit_at_3",
        "multi_all_hit_at_3",
        "multi_mrr",
        "mean_latency_ms",
        "median_latency_ms",
        "p95_latency_ms",
        "out_of_scope_count",
        "out_of_scope_top_distance_mean",
        "out_of_scope_top_distance_median",
        "out_of_scope_top_distance_min",
        "out_of_scope_top_distance_max",
        "api_cost_required",
        "external_api_required",
        "api_key_required",
        "local_execution",
        "offline_after_download",
        "question_type_counts",
        "provider_counts",
    ]
    write_csv(RESULT_DIR / "embedding_summary.csv", all_summaries, summary_fields)
    write_csv(
        RESULT_DIR / "embedding_by_question_type.csv",
        all_question_type_rows,
        ["experiment_id", "embedding_model", "embedding_type", "question_type", "count", "hit_rate_at_1", "hit_rate_at_3", "mrr"],
    )
    write_csv(
        RESULT_DIR / "embedding_by_provider.csv",
        all_provider_rows,
        ["experiment_id", "embedding_model", "embedding_type", "provider", "count", "hit_rate_at_1", "hit_rate_at_3", "mrr"],
    )
    tracked = [
        row
        for row in all_per_question
        if row["id"] in TRACKED_QUESTION_IDS or row["id"] in TRACKED_MULTI_IDS
    ]
    write_csv(RESULT_DIR / "embedding_tracked_questions.csv", tracked, PER_QUESTION_FIELDS)
    (RESULT_DIR / "embedding_summary.json").write_text(
        json.dumps(all_summaries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(all_summaries, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
