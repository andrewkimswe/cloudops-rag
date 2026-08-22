#!/usr/bin/env python3
"""Run Phase 13 held-out evaluation with frozen configuration and threshold."""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.evaluation.metrics import first_relevant_rank, hit_at_k, mean, reciprocal_rank
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore
from cloudops_rag.retrieval.schemas import RetrievedChunk


TEST_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_test.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "heldout"

EMBEDDING_MODEL = "text-embedding-3-small"
EVALUATION_DEPTH = 10
FINAL_THRESHOLD = 1.042478

FINAL_CONFIG = {
    "experiment_id": "frozen_final",
    "chunk_size": 1024,
    "chunk_overlap": 128,
    "chunk_unit": "character",
    "embedding_model": EMBEDDING_MODEL,
    "vector_db": "Chroma",
    "collection": "cloudops_rag_v1_embedding_openai_text_embedding_3_small",
    "configured_top_k": 5,
}

BASELINE_CONFIG = {
    "experiment_id": "original_baseline",
    "chunk_size": 512,
    "chunk_overlap": 0,
    "chunk_unit": "character",
    "embedding_model": EMBEDDING_MODEL,
    "vector_db": "Chroma",
    "collection": "cloudops_rag_v1_chunk_512_0",
    "configured_top_k": 3,
}

DEV_REFERENCE = {
    "retrieval": {
        "hit_at_1": "75.00% (27/36)",
        "hit_at_3": "91.67% (33/36)",
        "hit_at_5": "91.67% (33/36)",
        "mrr": 0.8408,
    },
    "threshold": {
        "in_scope_acceptance": "100.00% (36/36)",
        "out_of_scope_rejection": "100.00% (4/4)",
        "threshold": FINAL_THRESHOLD,
    },
}


def read_test_rows() -> list[dict[str, str]]:
    with TEST_EVALUATION_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def expected_docs(row: dict[str, str]) -> list[str]:
    return [
        doc
        for doc in [row["expected_document_1"].strip(), row["expected_document_2"].strip()]
        if doc and doc != "NONE"
    ]


def doc_list(chunks: list[RetrievedChunk], limit: int | None = None) -> str:
    scoped = chunks if limit is None else chunks[:limit]
    return "|".join(chunk.doc_id for chunk in scoped)


def chunk_list(chunks: list[RetrievedChunk], limit: int | None = None) -> str:
    scoped = chunks if limit is None else chunks[:limit]
    return "|".join(chunk.chunk_id for chunk in scoped)


def score_list(chunks: list[RetrievedChunk], limit: int | None = None) -> str:
    scoped = chunks if limit is None else chunks[:limit]
    return "|".join("" if chunk.score is None else f"{chunk.score:.6f}" for chunk in scoped)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def percentage(value: float) -> float:
    return round(value * 100, 2)


def first_rank_map(expected: list[str], retrieved_doc_ids: list[str]) -> dict[str, int | None]:
    output: dict[str, int | None] = {}
    for doc in expected:
        output[doc] = next((index for index, retrieved in enumerate(retrieved_doc_ids, start=1) if retrieved == doc), None)
    return output


def format_rank_map(ranks: dict[str, int | None]) -> str:
    return "|".join(f"{doc}:{rank if rank is not None else 'OUT'}" for doc, rank in ranks.items())


def diversity(chunks: list[RetrievedChunk], cutoff_k: int) -> dict[str, Any]:
    top = chunks[:cutoff_k]
    counts = Counter(chunk.doc_id for chunk in top)
    unique_doc_count = len(counts)
    duplicate_chunk_count = len(top) - unique_doc_count
    max_same_doc_occupancy = max(counts.values()) if counts else 0
    return {
        "unique_doc_count": unique_doc_count,
        "duplicate_chunk_count": duplicate_chunk_count,
        "duplicate_ratio": ratio(duplicate_chunk_count, len(top)),
        "max_same_doc_occupancy": max_same_doc_occupancy,
        "max_same_doc_occupancy_ratio": ratio(max_same_doc_occupancy, len(top)),
    }


def evaluate_config(
    config: dict[str, Any],
    rows: list[dict[str, str]],
    settings: Settings,
    embedder: OpenAIEmbedder,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    store = ChromaVectorStore(settings.chroma_persist_dir, config["collection"])
    per_question: list[dict[str, Any]] = []
    for row in rows:
        retrieved = store.retrieve(row["question"], embedder, top_k=EVALUATION_DEPTH)
        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved]
        expected = expected_docs(row)
        expected_set = set(expected)
        ranks = first_rank_map(expected, retrieved_doc_ids)
        is_out = row["ground_truth_type"] == "out_of_scope"
        configured_k = int(config["configured_top_k"])
        top_1_distance = float(retrieved[0].score) if retrieved and retrieved[0].score is not None else None
        accepted = top_1_distance is not None and top_1_distance <= FINAL_THRESHOLD
        div = diversity(retrieved, configured_k)
        result: dict[str, Any] = {
            "experiment_id": config["experiment_id"],
            "id": row["id"],
            "question": row["question"],
            "ground_truth_type": row["ground_truth_type"],
            "question_type": row["question_type"],
            "expected_document_1": row["expected_document_1"],
            "expected_document_2": row["expected_document_2"],
            "expected_documents": "|".join(expected),
            "configured_top_k": configured_k,
            "retrieved_rank_1_doc_id": retrieved[0].doc_id if len(retrieved) > 0 else "",
            "retrieved_rank_2_doc_id": retrieved[1].doc_id if len(retrieved) > 1 else "",
            "retrieved_rank_3_doc_id": retrieved[2].doc_id if len(retrieved) > 2 else "",
            "retrieved_rank_4_doc_id": retrieved[3].doc_id if len(retrieved) > 3 else "",
            "retrieved_rank_5_doc_id": retrieved[4].doc_id if len(retrieved) > 4 else "",
            "top_1_distance": top_1_distance,
            "top_3_doc_ids": doc_list(retrieved, 3),
            "top_5_doc_ids": doc_list(retrieved, 5),
            "top_10_doc_ids": doc_list(retrieved, 10),
            "top_5_chunk_ids": chunk_list(retrieved, 5),
            "top_5_distances": score_list(retrieved, 5),
            "first_expected_ranks": format_rank_map(ranks),
            "threshold": FINAL_THRESHOLD,
            "threshold_decision": "accept" if accepted else "reject",
            **div,
        }
        if is_out:
            result.update(
                {
                    "hit_at_1": "",
                    "hit_at_3": "",
                    "hit_at_5": "",
                    "any_hit_at_1": "",
                    "any_hit_at_3": "",
                    "any_hit_at_5": "",
                    "all_hit_at_1": "",
                    "all_hit_at_3": "",
                    "all_hit_at_5": "",
                    "reciprocal_rank": "",
                    "threshold_classification": "FA" if accepted else "TR",
                }
            )
        else:
            result.update(
                {
                    "hit_at_1": int(hit_at_k(expected_set, retrieved_doc_ids, 1)),
                    "hit_at_3": int(hit_at_k(expected_set, retrieved_doc_ids, 3)),
                    "hit_at_5": int(hit_at_k(expected_set, retrieved_doc_ids, 5)),
                    "any_hit_at_1": int(hit_at_k(expected_set, retrieved_doc_ids, 1)),
                    "any_hit_at_3": int(hit_at_k(expected_set, retrieved_doc_ids, 3)),
                    "any_hit_at_5": int(hit_at_k(expected_set, retrieved_doc_ids, 5)),
                    "all_hit_at_1": int(expected_set.issubset(set(retrieved_doc_ids[:1]))),
                    "all_hit_at_3": int(expected_set.issubset(set(retrieved_doc_ids[:3]))),
                    "all_hit_at_5": int(expected_set.issubset(set(retrieved_doc_ids[:5]))),
                    "reciprocal_rank": reciprocal_rank(expected_set, retrieved_doc_ids),
                    "threshold_classification": "TA" if accepted else "FR",
                }
            )
        per_question.append(result)

    summary = summarize_config(config, per_question)
    return per_question, summary


def summarize_config(config: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    in_scope = [row for row in rows if row["ground_truth_type"] != "out_of_scope"]
    single = [row for row in in_scope if row["ground_truth_type"] == "single"]
    multi = [row for row in in_scope if row["ground_truth_type"] == "multi"]
    out_scope = [row for row in rows if row["ground_truth_type"] == "out_of_scope"]
    threshold_counts = Counter(row["threshold_classification"] for row in rows)

    return {
        "experiment_id": config["experiment_id"],
        "chunk_size": config["chunk_size"],
        "chunk_overlap": config["chunk_overlap"],
        "chunk_unit": config["chunk_unit"],
        "embedding_model": config["embedding_model"],
        "vector_db": config["vector_db"],
        "collection": config["collection"],
        "configured_top_k": config["configured_top_k"],
        "threshold": FINAL_THRESHOLD,
        "test_total": len(rows),
        "in_scope_count": len(in_scope),
        "out_of_scope_count": len(out_scope),
        "single_count": len(single),
        "multi_count": len(multi),
        "hit_at_1_count": sum(int(row["hit_at_1"]) for row in in_scope),
        "hit_at_3_count": sum(int(row["hit_at_3"]) for row in in_scope),
        "hit_at_5_count": sum(int(row["hit_at_5"]) for row in in_scope),
        "hit_at_1_rate": ratio(sum(int(row["hit_at_1"]) for row in in_scope), len(in_scope)),
        "hit_at_3_rate": ratio(sum(int(row["hit_at_3"]) for row in in_scope), len(in_scope)),
        "hit_at_5_rate": ratio(sum(int(row["hit_at_5"]) for row in in_scope), len(in_scope)),
        "mrr": mean([float(row["reciprocal_rank"]) for row in in_scope]),
        "single_hit_at_1_count": sum(int(row["hit_at_1"]) for row in single),
        "single_hit_at_3_count": sum(int(row["hit_at_3"]) for row in single),
        "single_hit_at_5_count": sum(int(row["hit_at_5"]) for row in single),
        "single_hit_at_1_rate": ratio(sum(int(row["hit_at_1"]) for row in single), len(single)),
        "single_hit_at_3_rate": ratio(sum(int(row["hit_at_3"]) for row in single), len(single)),
        "single_hit_at_5_rate": ratio(sum(int(row["hit_at_5"]) for row in single), len(single)),
        "single_mrr": mean([float(row["reciprocal_rank"]) for row in single]),
        "multi_any_hit_at_1_count": sum(int(row["any_hit_at_1"]) for row in multi),
        "multi_any_hit_at_3_count": sum(int(row["any_hit_at_3"]) for row in multi),
        "multi_any_hit_at_5_count": sum(int(row["any_hit_at_5"]) for row in multi),
        "multi_all_hit_at_1_count": sum(int(row["all_hit_at_1"]) for row in multi),
        "multi_all_hit_at_3_count": sum(int(row["all_hit_at_3"]) for row in multi),
        "multi_all_hit_at_5_count": sum(int(row["all_hit_at_5"]) for row in multi),
        "multi_any_hit_at_1_rate": ratio(sum(int(row["any_hit_at_1"]) for row in multi), len(multi)),
        "multi_any_hit_at_3_rate": ratio(sum(int(row["any_hit_at_3"]) for row in multi), len(multi)),
        "multi_any_hit_at_5_rate": ratio(sum(int(row["any_hit_at_5"]) for row in multi), len(multi)),
        "multi_all_hit_at_1_rate": ratio(sum(int(row["all_hit_at_1"]) for row in multi), len(multi)),
        "multi_all_hit_at_3_rate": ratio(sum(int(row["all_hit_at_3"]) for row in multi), len(multi)),
        "multi_all_hit_at_5_rate": ratio(sum(int(row["all_hit_at_5"]) for row in multi), len(multi)),
        "multi_mrr": mean([float(row["reciprocal_rank"]) for row in multi]),
        "true_accept": threshold_counts["TA"],
        "false_reject": threshold_counts["FR"],
        "true_reject": threshold_counts["TR"],
        "false_accept": threshold_counts["FA"],
        "in_scope_acceptance_rate": ratio(threshold_counts["TA"], len(in_scope)),
        "out_of_scope_rejection_rate": ratio(threshold_counts["TR"], len(out_scope)),
        "false_reject_rate": ratio(threshold_counts["FR"], len(in_scope)),
        "false_accept_rate": ratio(threshold_counts["FA"], len(out_scope)),
        "avg_unique_doc_count": mean([float(row["unique_doc_count"]) for row in rows]),
        "avg_duplicate_chunk_count": mean([float(row["duplicate_chunk_count"]) for row in rows]),
        "avg_duplicate_ratio": mean([float(row["duplicate_ratio"]) for row in rows]),
        "avg_same_doc_occupancy": mean([float(row["max_same_doc_occupancy"]) for row in rows]),
        "max_same_doc_occupancy": max([int(row["max_same_doc_occupancy"]) for row in rows], default=0),
    }


def failure_category(row: dict[str, Any]) -> str:
    if row["threshold_classification"] == "FR":
        return "threshold false reject"
    if row["threshold_classification"] == "FA":
        return "threshold false accept"
    if row["ground_truth_type"] == "multi" and row["all_hit_at_5"] == 0:
        if row["duplicate_ratio"] >= 0.4:
            return "multi-document incomplete; duplicate document chunks"
        return "multi-document incomplete"
    if row["hit_at_5"] == 0:
        ranks = row["first_expected_ranks"]
        if "OUT" not in ranks:
            return "expected document below cutoff"
        return "wrong semantic neighbor"
    if row["hit_at_1"] == 0:
        return "ranking weakness"
    return ""


def build_failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row in rows:
        category = failure_category(row)
        if not category:
            continue
        failures.append(
            {
                "id": row["id"],
                "question": row["question"],
                "ground_truth_type": row["ground_truth_type"],
                "expected_documents": row["expected_documents"],
                "top_1_doc_id": row["retrieved_rank_1_doc_id"],
                "top_5_doc_ids": row["top_5_doc_ids"],
                "first_expected_ranks": row["first_expected_ranks"],
                "top_1_distance": row["top_1_distance"],
                "threshold_decision": row["threshold_decision"],
                "threshold_classification": row["threshold_classification"],
                "failure_category": category,
                "similar_to_dev_failure_mode": "yes"
                if category
                in {
                    "multi-document incomplete; duplicate document chunks",
                    "multi-document incomplete",
                    "wrong semantic neighbor",
                    "ranking weakness",
                }
                else "no",
            }
        )
    return failures


def main() -> int:
    settings = Settings.from_env()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_test_rows()
    embedder = OpenAIEmbedder(model=EMBEDDING_MODEL, api_key=settings.openai_api_key)

    final_rows, final_summary = evaluate_config(FINAL_CONFIG, rows, settings, embedder)
    baseline_rows, baseline_summary = evaluate_config(BASELINE_CONFIG, rows, settings, embedder)

    per_fields = [
        "experiment_id",
        "id",
        "question",
        "ground_truth_type",
        "question_type",
        "expected_document_1",
        "expected_document_2",
        "expected_documents",
        "configured_top_k",
        "retrieved_rank_1_doc_id",
        "retrieved_rank_2_doc_id",
        "retrieved_rank_3_doc_id",
        "retrieved_rank_4_doc_id",
        "retrieved_rank_5_doc_id",
        "top_1_distance",
        "top_3_doc_ids",
        "top_5_doc_ids",
        "top_10_doc_ids",
        "top_5_chunk_ids",
        "top_5_distances",
        "first_expected_ranks",
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "any_hit_at_1",
        "any_hit_at_3",
        "any_hit_at_5",
        "all_hit_at_1",
        "all_hit_at_3",
        "all_hit_at_5",
        "reciprocal_rank",
        "threshold",
        "threshold_decision",
        "threshold_classification",
        "unique_doc_count",
        "duplicate_chunk_count",
        "duplicate_ratio",
        "max_same_doc_occupancy",
        "max_same_doc_occupancy_ratio",
    ]
    summary_fields = list(final_summary.keys())
    all_rows = final_rows + baseline_rows
    summaries = [final_summary, baseline_summary]
    failures = build_failures(final_rows)

    threshold_rows = [
        {
            "id": row["id"],
            "question": row["question"],
            "scope": "out_of_scope" if row["ground_truth_type"] == "out_of_scope" else "in_scope",
            "top_1_distance": row["top_1_distance"],
            "threshold": row["threshold"],
            "threshold_decision": row["threshold_decision"],
            "threshold_classification": row["threshold_classification"],
            "top_1_doc_id": row["retrieved_rank_1_doc_id"],
            "distance_margin": float(row["top_1_distance"]) - FINAL_THRESHOLD,
            "absolute_margin": abs(float(row["top_1_distance"]) - FINAL_THRESHOLD),
        }
        for row in final_rows
    ]
    diversity_rows = [
        {
            "id": row["id"],
            "question": row["question"],
            "ground_truth_type": row["ground_truth_type"],
            "question_type": row["question_type"],
            "expected_documents": row["expected_documents"],
            "top_5_doc_ids": row["top_5_doc_ids"],
            "unique_doc_count": row["unique_doc_count"],
            "duplicate_chunk_count": row["duplicate_chunk_count"],
            "duplicate_ratio": row["duplicate_ratio"],
            "max_same_doc_occupancy": row["max_same_doc_occupancy"],
            "max_same_doc_occupancy_ratio": row["max_same_doc_occupancy_ratio"],
        }
        for row in final_rows
    ]
    baseline_vs_final = [
        {
            "metric": "configured_cutoff_hit",
            "baseline": f"{baseline_summary['hit_at_3_count']}/{baseline_summary['in_scope_count']}",
            "baseline_rate": baseline_summary["hit_at_3_rate"],
            "final": f"{final_summary['hit_at_5_count']}/{final_summary['in_scope_count']}",
            "final_rate": final_summary["hit_at_5_rate"],
        },
        {
            "metric": "hit_at_1",
            "baseline": f"{baseline_summary['hit_at_1_count']}/{baseline_summary['in_scope_count']}",
            "baseline_rate": baseline_summary["hit_at_1_rate"],
            "final": f"{final_summary['hit_at_1_count']}/{final_summary['in_scope_count']}",
            "final_rate": final_summary["hit_at_1_rate"],
        },
        {
            "metric": "mrr",
            "baseline": baseline_summary["mrr"],
            "baseline_rate": baseline_summary["mrr"],
            "final": final_summary["mrr"],
            "final_rate": final_summary["mrr"],
        },
        {
            "metric": "multi_all_hit_configured_cutoff",
            "baseline": f"{baseline_summary['multi_all_hit_at_3_count']}/{baseline_summary['multi_count']}",
            "baseline_rate": baseline_summary["multi_all_hit_at_3_rate"],
            "final": f"{final_summary['multi_all_hit_at_5_count']}/{final_summary['multi_count']}",
            "final_rate": final_summary["multi_all_hit_at_5_rate"],
        },
    ]

    write_csv(RESULT_DIR / "heldout_per_question.csv", all_rows, per_fields)
    write_csv(RESULT_DIR / "heldout_baseline_vs_final.csv", baseline_vs_final, ["metric", "baseline", "baseline_rate", "final", "final_rate"])
    write_csv(
        RESULT_DIR / "heldout_threshold.csv",
        threshold_rows,
        [
            "id",
            "question",
            "scope",
            "top_1_distance",
            "threshold",
            "threshold_decision",
            "threshold_classification",
            "top_1_doc_id",
            "distance_margin",
            "absolute_margin",
        ],
    )
    write_csv(
        RESULT_DIR / "heldout_failures.csv",
        failures,
        [
            "id",
            "question",
            "ground_truth_type",
            "expected_documents",
            "top_1_doc_id",
            "top_5_doc_ids",
            "first_expected_ranks",
            "top_1_distance",
            "threshold_decision",
            "threshold_classification",
            "failure_category",
            "similar_to_dev_failure_mode",
        ],
    )
    write_csv(
        RESULT_DIR / "heldout_document_diversity.csv",
        diversity_rows,
        [
            "id",
            "question",
            "ground_truth_type",
            "question_type",
            "expected_documents",
            "top_5_doc_ids",
            "unique_doc_count",
            "duplicate_chunk_count",
            "duplicate_ratio",
            "max_same_doc_occupancy",
            "max_same_doc_occupancy_ratio",
        ],
    )
    write_csv(RESULT_DIR / "heldout_summary.csv", summaries, summary_fields)

    metadata = {
        "phase": "Phase 13",
        "test_dataset": str(TEST_EVALUATION_PATH.relative_to(PROJECT_ROOT)),
        "configuration_retuned": False,
        "threshold_retuned": False,
        "answer_quality_evaluated": False,
        "dev_reference": DEV_REFERENCE,
        "frozen_final_summary": final_summary,
        "original_baseline_summary": baseline_summary,
        "failure_count": len(failures),
        "failure_categories": dict(Counter(row["failure_category"] for row in failures)),
    }
    (RESULT_DIR / "heldout_summary.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
