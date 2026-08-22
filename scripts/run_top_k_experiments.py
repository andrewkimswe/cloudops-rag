#!/usr/bin/env python3
"""Run Phase 10 Top-k retrieval experiments on the development set only."""

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
from cloudops_rag.evaluation.metrics import (
    first_relevant_rank,
    hit_at_k,
    mean,
    multi_all_hit_at_k,
    multi_any_hit_at_k,
    reciprocal_rank,
)
from cloudops_rag.ingestion.loader import load_processed_documents
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore
from cloudops_rag.retrieval.schemas import RetrievedChunk


DEV_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_dev.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "top_k"

EXPERIMENT_ID = "top_k_openai_1024_128"
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128
CHUNK_UNIT = "character"
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_DB = "Chroma"
BASE_CUTOFFS = [1, 3, 5]
EVALUATION_DEPTH = 10
TRACKED_PERSISTENT_IDS = {"eval_002", "eval_007", "eval_019", "eval_027"}
TRACKED_MULTI_IDS = {"eval_021", "eval_023", "eval_024"}


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


def percentage(value: float) -> float:
    return round(value * 100, 2)


def ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * percentile_value))
    return sorted_values[index]


def first_rank_for_doc(doc_id: str, retrieved_doc_ids: list[str]) -> int | None:
    for index, retrieved_doc_id in enumerate(retrieved_doc_ids, start=1):
        if retrieved_doc_id == doc_id:
            return index
    return None


def first_expected_ranks(expected: list[str], retrieved_doc_ids: list[str]) -> dict[str, int | None]:
    return {doc_id: first_rank_for_doc(doc_id, retrieved_doc_ids) for doc_id in expected}


def format_rank(rank: int | None) -> str:
    return str(rank) if rank is not None else "OUT"


def format_rank_map(ranks: dict[str, int | None]) -> str:
    return "|".join(f"{doc_id}:{format_rank(rank)}" for doc_id, rank in ranks.items())


def doc_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join(chunk.doc_id for chunk in chunks)


def chunk_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join(chunk.chunk_id for chunk in chunks)


def title_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join(chunk.title for chunk in chunks)


def score_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join("" if chunk.score is None else str(round(chunk.score, 6)) for chunk in chunks)


def diversity(chunks: list[RetrievedChunk], cutoff_k: int) -> dict[str, Any]:
    top = chunks[:cutoff_k]
    doc_ids = [chunk.doc_id for chunk in top]
    counts = Counter(doc_ids)
    unique_doc_count = len(counts)
    duplicate_chunk_count = len(top) - unique_doc_count
    max_occupancy = max(counts.values()) if counts else 0
    return {
        "unique_doc_count": unique_doc_count,
        "duplicate_chunk_count": duplicate_chunk_count,
        "duplicate_ratio": ratio(duplicate_chunk_count, len(top)),
        "max_same_doc_occupancy": max_occupancy,
        "max_same_doc_occupancy_ratio": ratio(max_occupancy, len(top)),
    }


def context_size(chunks: list[RetrievedChunk], cutoff_k: int) -> dict[str, Any]:
    top = chunks[:cutoff_k]
    char_count = sum(len(chunk.chunk) for chunk in top)
    return {
        "retrieved_chunk_count": len(top),
        "retrieved_character_count": char_count,
        "approximate_token_count": round(char_count / 4),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def ensure_index(settings: Settings, embedder: OpenAIEmbedder) -> tuple[int, int, bool, float]:
    documents = load_processed_documents(settings.processed_dir)
    chunks = chunk_documents(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunk_count = len(chunks)
    collection_name = f"{settings.chroma_collection}_embedding_openai_text_embedding_3_small"
    store = ChromaVectorStore(settings.chroma_persist_dir, collection_name)
    existing_count = store.collection.count()
    if existing_count == chunk_count:
        return chunk_count, existing_count, False, 0.0

    started = time.perf_counter()
    indexed_count = store.index_chunks(chunks, embedder, reset=True)
    indexing_time_ms = (time.perf_counter() - started) * 1000
    return chunk_count, indexed_count, True, indexing_time_ms


def retrieve_depth_10(
    rows: list[dict[str, str]],
    settings: Settings,
    embedder: OpenAIEmbedder,
) -> tuple[dict[str, list[RetrievedChunk]], dict[str, float]]:
    collection_name = f"{settings.chroma_collection}_embedding_openai_text_embedding_3_small"
    store = ChromaVectorStore(settings.chroma_persist_dir, collection_name)
    retrieved_by_id: dict[str, list[RetrievedChunk]] = {}
    latency_by_id: dict[str, float] = {}
    for row in rows:
        started = time.perf_counter()
        retrieved_by_id[row["id"]] = store.retrieve(row["question"], embedder, top_k=EVALUATION_DEPTH)
        latency_by_id[row["id"]] = (time.perf_counter() - started) * 1000
    return retrieved_by_id, latency_by_id


def should_add_k10(rows: list[dict[str, str]], retrieved_by_id: dict[str, list[RetrievedChunk]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    multi_rows = [row for row in rows if row["ground_truth_type"] == "multi"]
    all_hit_at_5 = [
        multi_all_hit_at_k(set(expected_docs(row)), [chunk.doc_id for chunk in retrieved_by_id[row["id"]]], 5)
        for row in multi_rows
    ]
    if all_hit_at_5 and not all(all_hit_at_5):
        reasons.append("multi_all_hit_at_5_below_100_percent")

    for row in multi_rows:
        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved_by_id[row["id"]]]
        ranks = first_expected_ranks(expected_docs(row), retrieved_doc_ids)
        if any(rank is not None and 6 <= rank <= 10 for rank in ranks.values()):
            reasons.append("multi_expected_doc_ranked_6_to_10")
            break

    for question_id in TRACKED_PERSISTENT_IDS:
        row = next((item for item in rows if item["id"] == question_id), None)
        if row is None:
            continue
        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved_by_id[question_id]]
        ranks = first_expected_ranks(expected_docs(row), retrieved_doc_ids)
        if any(rank is not None and 6 <= rank <= 10 for rank in ranks.values()):
            reasons.append("tracked_persistent_expected_doc_ranked_6_to_10")
            break
    return bool(reasons), sorted(set(reasons))


def per_question_rows(
    rows: list[dict[str, str]],
    retrieved_by_id: dict[str, list[RetrievedChunk]],
    latency_by_id: dict[str, float],
    cutoffs: list[int],
    provider_by_doc_id: dict[str, str],
    chunk_count: int,
    index_was_rebuilt: bool,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        retrieved = retrieved_by_id[row["id"]]
        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved]
        expected = expected_docs(row)
        expected_set = set(expected)
        ranks = first_expected_ranks(expected, retrieved_doc_ids)
        is_out_of_scope = row["ground_truth_type"] == "out_of_scope"
        for cutoff_k in cutoffs:
            top = retrieved[:cutoff_k]
            div = diversity(retrieved, cutoff_k)
            ctx = context_size(retrieved, cutoff_k)
            base = {
                "experiment_id": EXPERIMENT_ID,
                "cutoff_k": cutoff_k,
                "evaluation_depth": EVALUATION_DEPTH,
                "same_ranking_cutoff": True,
                "embedding_model": EMBEDDING_MODEL,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "chunk_unit": CHUNK_UNIT,
                "chunk_count": chunk_count,
                "index_was_rebuilt": index_was_rebuilt,
                "id": row["id"],
                "question": row["question"],
                "ground_truth_type": row["ground_truth_type"],
                "question_type": row["question_type"],
                "provider": provider_for_row(row, provider_by_doc_id),
                "expected_document_1": row["expected_document_1"],
                "expected_document_2": row["expected_document_2"],
                "expected_documents": "|".join(expected),
                "retrieved_doc_ids": doc_list(top),
                "retrieved_chunk_ids": chunk_list(top),
                "retrieved_titles": title_list(top),
                "retrieved_scores": score_list(top),
                "top_1_doc_id": top[0].doc_id if top else "",
                "top_3_doc_ids": doc_list(retrieved[:3]),
                "top_5_doc_ids": doc_list(retrieved[:5]),
                "top_10_doc_ids": doc_list(retrieved[:10]),
                "first_expected_rank_1": format_rank(ranks.get(expected[0])) if len(expected) > 0 else "",
                "first_expected_rank_2": format_rank(ranks.get(expected[1])) if len(expected) > 1 else "",
                "first_expected_ranks": format_rank_map(ranks),
                "retrieval_latency_depth10_ms": round(latency_by_id[row["id"]], 3),
                **div,
                **ctx,
            }
            if is_out_of_scope:
                base.update(
                    {
                        "hit_at_k": "",
                        "any_hit_at_k": "",
                        "all_hit_at_k": "",
                        "reciprocal_rank": "",
                    }
                )
            else:
                base.update(
                    {
                        "hit_at_k": int(hit_at_k(expected_set, retrieved_doc_ids, cutoff_k)),
                        "any_hit_at_k": int(multi_any_hit_at_k(expected_set, retrieved_doc_ids, cutoff_k)),
                        "all_hit_at_k": int(multi_all_hit_at_k(expected_set, retrieved_doc_ids, cutoff_k)),
                        "reciprocal_rank": reciprocal_rank(expected_set, retrieved_doc_ids),
                    }
                )
            output.append(base)
    return output


def summarize_cutoff(rows: list[dict[str, Any]], cutoff_k: int, chunk_count: int, indexed_count: int, index_was_rebuilt: bool) -> dict[str, Any]:
    scoped = [row for row in rows if row["cutoff_k"] == cutoff_k]
    in_scope = [row for row in scoped if row["ground_truth_type"] != "out_of_scope"]
    single = [row for row in in_scope if row["ground_truth_type"] == "single"]
    multi = [row for row in in_scope if row["ground_truth_type"] == "multi"]

    hit_count = sum(int(row["hit_at_k"]) for row in in_scope)
    single_hit_count = sum(int(row["hit_at_k"]) for row in single)
    multi_any_count = sum(int(row["any_hit_at_k"]) for row in multi)
    multi_all_count = sum(int(row["all_hit_at_k"]) for row in multi)
    return {
        "experiment_id": EXPERIMENT_ID,
        "cutoff_k": cutoff_k,
        "evaluation_depth": EVALUATION_DEPTH,
        "same_ranking_cutoff": True,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "chunk_unit": CHUNK_UNIT,
        "chunk_count": chunk_count,
        "indexed_count": indexed_count,
        "index_was_rebuilt": index_was_rebuilt,
        "in_scope_count": len(in_scope),
        "overall_hit_count": hit_count,
        "overall_hit_rate": ratio(hit_count, len(in_scope)),
        "overall_hit_percent": percentage(ratio(hit_count, len(in_scope))),
        "overall_mrr": mean([float(row["reciprocal_rank"]) for row in in_scope]),
        "single_count": len(single),
        "single_hit_count": single_hit_count,
        "single_hit_rate": ratio(single_hit_count, len(single)),
        "single_hit_percent": percentage(ratio(single_hit_count, len(single))),
        "single_mrr": mean([float(row["reciprocal_rank"]) for row in single]),
        "multi_count": len(multi),
        "multi_any_hit_count": multi_any_count,
        "multi_any_hit_rate": ratio(multi_any_count, len(multi)),
        "multi_any_hit_percent": percentage(ratio(multi_any_count, len(multi))),
        "multi_all_hit_count": multi_all_count,
        "multi_all_hit_rate": ratio(multi_all_count, len(multi)),
        "multi_all_hit_percent": percentage(ratio(multi_all_count, len(multi))),
        "multi_mrr": mean([float(row["reciprocal_rank"]) for row in multi]),
        "avg_unique_doc_count": mean([float(row["unique_doc_count"]) for row in scoped]),
        "avg_duplicate_chunk_count": mean([float(row["duplicate_chunk_count"]) for row in scoped]),
        "avg_duplicate_ratio": mean([float(row["duplicate_ratio"]) for row in scoped]),
        "avg_same_doc_occupancy": mean([float(row["max_same_doc_occupancy"]) for row in scoped]),
        "max_same_doc_occupancy": max([int(row["max_same_doc_occupancy"]) for row in scoped], default=0),
        "avg_same_doc_occupancy_ratio": mean([float(row["max_same_doc_occupancy_ratio"]) for row in scoped]),
        "avg_retrieved_chunk_count": mean([float(row["retrieved_chunk_count"]) for row in scoped]),
        "avg_retrieved_character_count": mean([float(row["retrieved_character_count"]) for row in scoped]),
        "avg_approximate_token_count": mean([float(row["approximate_token_count"]) for row in scoped]),
        "latency_depth10_mean_ms": mean([float(row["retrieval_latency_depth10_ms"]) for row in scoped]),
        "latency_depth10_median_ms": statistics.median([float(row["retrieval_latency_depth10_ms"]) for row in scoped]),
        "latency_depth10_p95_ms": percentile([float(row["retrieval_latency_depth10_ms"]) for row in scoped], 0.95),
    }


def grouped_summary(rows: list[dict[str, Any]], group_key: str, cutoffs: list[int]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for cutoff_k in cutoffs:
        scoped = [row for row in rows if row["cutoff_k"] == cutoff_k and row["ground_truth_type"] != "out_of_scope"]
        for group_value in sorted({row[group_key] for row in scoped}):
            group_rows = [row for row in scoped if row[group_key] == group_value]
            hit_count = sum(int(row["hit_at_k"]) for row in group_rows)
            output.append(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "cutoff_k": cutoff_k,
                    group_key: group_value,
                    "count": len(group_rows),
                    "hit_count": hit_count,
                    "hit_rate": ratio(hit_count, len(group_rows)),
                    "hit_percent": percentage(ratio(hit_count, len(group_rows))),
                    "mrr": mean([float(row["reciprocal_rank"]) for row in group_rows]),
                }
            )
    return output


def aggregate_rows(rows: list[dict[str, Any]], cutoffs: list[int], fields: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for cutoff_k in cutoffs:
        scoped = [row for row in rows if row["cutoff_k"] == cutoff_k]
        output.append(
            {
                "experiment_id": EXPERIMENT_ID,
                "cutoff_k": cutoff_k,
                **{f"avg_{field}": mean([float(row[field]) for row in scoped]) for field in fields},
                **{f"max_{field}": max([float(row[field]) for row in scoped], default=0.0) for field in fields},
            }
        )
    return output


def select_top_k(summary_rows: list[dict[str, Any]]) -> tuple[int, str]:
    by_k = {int(row["cutoff_k"]): row for row in summary_rows}
    k3 = by_k[3]
    k5 = by_k[5]
    coverage_gain = float(k5["overall_hit_rate"]) - float(k3["overall_hit_rate"])
    multi_all_gain = float(k5["multi_all_hit_rate"]) - float(k3["multi_all_hit_rate"])
    context_growth = float(k5["avg_approximate_token_count"]) - float(k3["avg_approximate_token_count"])
    if coverage_gain > 0.02 or multi_all_gain > 0.10:
        return 5, "k=5 improves retrieval coverage enough to justify the larger context."
    return 3, (
        "k=5 does not improve overall coverage or multi-document all-hit enough to justify "
        f"about {context_growth:.0f} additional approximate tokens per query."
    )


def main() -> int:
    settings = Settings.from_env()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_dev_rows()
    manifest = load_manifest(settings.manifest_path)
    provider_by_doc_id = {doc.doc_id: doc.provider for doc in manifest}

    embedder = OpenAIEmbedder(model=EMBEDDING_MODEL, api_key=settings.openai_api_key)
    chunk_count, indexed_count, index_was_rebuilt, indexing_time_ms = ensure_index(settings, embedder)
    retrieved_by_id, latency_by_id = retrieve_depth_10(rows, settings, embedder)
    add_k10, k10_reasons = should_add_k10(rows, retrieved_by_id)
    cutoffs = BASE_CUTOFFS + ([10] if add_k10 else [])

    per_rows = per_question_rows(
        rows,
        retrieved_by_id,
        latency_by_id,
        cutoffs,
        provider_by_doc_id,
        chunk_count,
        index_was_rebuilt,
    )
    summary_rows = [summarize_cutoff(per_rows, cutoff, chunk_count, indexed_count, index_was_rebuilt) for cutoff in cutoffs]
    for row in summary_rows:
        row["indexing_time_ms"] = round(indexing_time_ms, 3)
        row["diagnostic_k10_added"] = add_k10
        row["diagnostic_k10_reasons"] = "|".join(k10_reasons)

    selected_k, selection_rationale = select_top_k(summary_rows)
    metadata = {
        "phase": "Phase 10",
        "experiment_id": EXPERIMENT_ID,
        "evaluation_dataset": str(DEV_EVALUATION_PATH.relative_to(PROJECT_ROOT)),
        "held_out_test_used": False,
        "llm_answer_quality_evaluated": False,
        "retrieval_algorithm_changed": False,
        "evaluation_depth": EVALUATION_DEPTH,
        "cutoffs": cutoffs,
        "diagnostic_k10_added": add_k10,
        "diagnostic_k10_reasons": k10_reasons,
        "selected_top_k": selected_k,
        "selection_rationale": selection_rationale,
    }

    multi_rows = [
        row
        for row in per_rows
        if row["ground_truth_type"] == "multi" and row["id"] in TRACKED_MULTI_IDS
    ]
    tracked_rows = [
        row
        for row in per_rows
        if row["id"] in TRACKED_MULTI_IDS or row["id"] in TRACKED_PERSISTENT_IDS
    ]
    context_rows = aggregate_rows(
        per_rows,
        cutoffs,
        ["retrieved_chunk_count", "retrieved_character_count", "approximate_token_count"],
    )
    diversity_rows = aggregate_rows(
        per_rows,
        cutoffs,
        ["unique_doc_count", "duplicate_chunk_count", "duplicate_ratio", "max_same_doc_occupancy", "max_same_doc_occupancy_ratio"],
    )

    per_fields = [
        "experiment_id",
        "cutoff_k",
        "evaluation_depth",
        "same_ranking_cutoff",
        "embedding_model",
        "chunk_size",
        "chunk_overlap",
        "chunk_unit",
        "chunk_count",
        "index_was_rebuilt",
        "id",
        "question",
        "ground_truth_type",
        "question_type",
        "provider",
        "expected_document_1",
        "expected_document_2",
        "expected_documents",
        "retrieved_doc_ids",
        "retrieved_chunk_ids",
        "retrieved_titles",
        "retrieved_scores",
        "top_1_doc_id",
        "top_3_doc_ids",
        "top_5_doc_ids",
        "top_10_doc_ids",
        "first_expected_rank_1",
        "first_expected_rank_2",
        "first_expected_ranks",
        "hit_at_k",
        "any_hit_at_k",
        "all_hit_at_k",
        "reciprocal_rank",
        "unique_doc_count",
        "duplicate_chunk_count",
        "duplicate_ratio",
        "max_same_doc_occupancy",
        "max_same_doc_occupancy_ratio",
        "retrieved_chunk_count",
        "retrieved_character_count",
        "approximate_token_count",
        "retrieval_latency_depth10_ms",
    ]
    summary_fields = [
        "experiment_id",
        "cutoff_k",
        "evaluation_depth",
        "same_ranking_cutoff",
        "embedding_model",
        "chunk_size",
        "chunk_overlap",
        "chunk_unit",
        "chunk_count",
        "indexed_count",
        "index_was_rebuilt",
        "indexing_time_ms",
        "diagnostic_k10_added",
        "diagnostic_k10_reasons",
        "in_scope_count",
        "overall_hit_count",
        "overall_hit_rate",
        "overall_hit_percent",
        "overall_mrr",
        "single_count",
        "single_hit_count",
        "single_hit_rate",
        "single_hit_percent",
        "single_mrr",
        "multi_count",
        "multi_any_hit_count",
        "multi_any_hit_rate",
        "multi_any_hit_percent",
        "multi_all_hit_count",
        "multi_all_hit_rate",
        "multi_all_hit_percent",
        "multi_mrr",
        "avg_unique_doc_count",
        "avg_duplicate_chunk_count",
        "avg_duplicate_ratio",
        "avg_same_doc_occupancy",
        "max_same_doc_occupancy",
        "avg_same_doc_occupancy_ratio",
        "avg_retrieved_chunk_count",
        "avg_retrieved_character_count",
        "avg_approximate_token_count",
        "latency_depth10_mean_ms",
        "latency_depth10_median_ms",
        "latency_depth10_p95_ms",
    ]

    write_csv(RESULT_DIR / "top_k_summary.csv", summary_rows, summary_fields)
    write_csv(RESULT_DIR / "top_k_per_question.csv", per_rows, per_fields)
    write_csv(
        RESULT_DIR / "top_k_by_question_type.csv",
        grouped_summary(per_rows, "question_type", cutoffs),
        ["experiment_id", "cutoff_k", "question_type", "count", "hit_count", "hit_rate", "hit_percent", "mrr"],
    )
    write_csv(
        RESULT_DIR / "top_k_by_provider.csv",
        grouped_summary(per_rows, "provider", cutoffs),
        ["experiment_id", "cutoff_k", "provider", "count", "hit_count", "hit_rate", "hit_percent", "mrr"],
    )
    write_csv(RESULT_DIR / "top_k_multi_document.csv", multi_rows, per_fields)
    write_csv(RESULT_DIR / "top_k_tracked_questions.csv", tracked_rows, per_fields)
    write_csv(
        RESULT_DIR / "top_k_context_analysis.csv",
        context_rows,
        [
            "experiment_id",
            "cutoff_k",
            "avg_retrieved_chunk_count",
            "avg_retrieved_character_count",
            "avg_approximate_token_count",
            "max_retrieved_chunk_count",
            "max_retrieved_character_count",
            "max_approximate_token_count",
        ],
    )
    write_csv(
        RESULT_DIR / "top_k_document_diversity.csv",
        diversity_rows,
        [
            "experiment_id",
            "cutoff_k",
            "avg_unique_doc_count",
            "avg_duplicate_chunk_count",
            "avg_duplicate_ratio",
            "avg_max_same_doc_occupancy",
            "avg_max_same_doc_occupancy_ratio",
            "max_unique_doc_count",
            "max_duplicate_chunk_count",
            "max_duplicate_ratio",
            "max_max_same_doc_occupancy",
            "max_max_same_doc_occupancy_ratio",
        ],
    )
    (RESULT_DIR / "top_k_summary.json").write_text(
        json.dumps({"metadata": metadata, "summary": summary_rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"metadata": metadata, "summary": summary_rows}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
