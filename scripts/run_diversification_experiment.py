#!/usr/bin/env python3
"""Run a Dev-only retrieval diversification controlled experiment."""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.api.config import (
    FROZEN_CHUNK_OVERLAP,
    FROZEN_CHUNK_SIZE,
    FROZEN_CHUNK_UNIT,
    FROZEN_EMBEDDING_MODEL,
    FROZEN_EVALUATION_CHROMA_COLLECTION,
    FROZEN_RETRIEVAL_TOP_K,
    FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
)
from cloudops_rag.config.settings import Settings, load_dotenv_file
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.evaluation.metrics import hit_at_k, mean, multi_all_hit_at_k, multi_any_hit_at_k, reciprocal_rank
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore
from cloudops_rag.retrieval.diversification import document_diversity, select_with_per_document_cap
from cloudops_rag.retrieval.schemas import RetrievedChunk

DEV_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_dev.csv"
FULL_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_full.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "diversification"
RAW_RETRIEVAL_DEPTH = 20
FINAL_TOP_K = FROZEN_RETRIEVAL_TOP_K
PER_DOCUMENT_CAP = 2
APPROX_TOKEN_DIVISOR = 4
HARD_CASE_IDS = {"eval_007", "eval_027", "eval_043", "eval_045", "eval_046"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def expected_docs(row: dict[str, str]) -> list[str]:
    return [doc for doc in [row.get("expected_document_1", "").strip(), row.get("expected_document_2", "").strip()] if doc and doc != "NONE"]


def provider_for_row(row: dict[str, str], provider_by_doc_id: dict[str, str]) -> str:
    docs = expected_docs(row)
    if not docs:
        return "out_of_scope"
    providers = {provider_by_doc_id[doc] for doc in docs if doc in provider_by_doc_id}
    if len(providers) == 1:
        return next(iter(providers))
    return "mixed"


def doc_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join(chunk.doc_id for chunk in chunks)


def chunk_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join(chunk.chunk_id for chunk in chunks)


def score_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join("" if chunk.score is None else str(round(chunk.score, 6)) for chunk in chunks)


def context_stats(chunks: list[RetrievedChunk]) -> dict[str, Any]:
    chars = sum(len(chunk.chunk) for chunk in chunks)
    return {
        "retrieved_chunk_count": len(chunks),
        "context_character_count": chars,
        "approximate_token_count": round(chars / APPROX_TOKEN_DIVISOR),
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * p))
    return sorted_values[index]


def first_expected_ranks(expected: list[str], retrieved_doc_ids: list[str]) -> dict[str, int | None]:
    ranks: dict[str, int | None] = {}
    for doc_id in expected:
        ranks[doc_id] = next((index for index, retrieved in enumerate(retrieved_doc_ids, start=1) if retrieved == doc_id), None)
    return ranks


def first_missing_rank(expected: list[str], selected_doc_ids: list[str], raw_doc_ids: list[str]) -> str:
    missing = [doc for doc in expected if doc not in set(selected_doc_ids)]
    pieces = []
    for doc_id in missing:
        rank = next((index for index, raw_doc_id in enumerate(raw_doc_ids, start=1) if raw_doc_id == doc_id), None)
        pieces.append(f"{doc_id}:{rank if rank is not None else 'not_in_raw_depth'}")
    return "|".join(pieces)


def result_for_variant(row: dict[str, str], chunks: list[RetrievedChunk], variant: str, latency_ms: float, provider: str) -> dict[str, Any]:
    selected_doc_ids = [chunk.doc_id for chunk in chunks]
    expected = expected_docs(row)
    expected_set = set(expected)
    is_out_of_scope = row["ground_truth_type"] == "out_of_scope"
    div = document_diversity(selected_doc_ids)
    ctx = context_stats(chunks)
    base: dict[str, Any] = {
        "variant": variant,
        "id": row["id"],
        "question": row["question"],
        "ground_truth_type": row["ground_truth_type"],
        "question_type": row["question_type"],
        "provider": provider,
        "expected_documents": "|".join(expected),
        "expected_document_1": row.get("expected_document_1", ""),
        "expected_document_2": row.get("expected_document_2", ""),
        "retrieved_doc_ids": doc_list(chunks),
        "retrieved_chunk_ids": chunk_list(chunks),
        "retrieved_scores": score_list(chunks),
        "top_1_doc_id": chunks[0].doc_id if chunks else "",
        "top_3_doc_ids": doc_list(chunks[:3]),
        "top_5_doc_ids": doc_list(chunks[:5]),
        "reciprocal_rank": "" if is_out_of_scope else reciprocal_rank(expected_set, selected_doc_ids),
        "retrieval_latency_ms": round(latency_ms, 3),
        **div,
        **ctx,
    }
    if is_out_of_scope:
        for name in ["hit_at_1", "hit_at_3", "hit_at_5", "any_hit_at_1", "any_hit_at_3", "any_hit_at_5", "all_hit_at_1", "all_hit_at_3", "all_hit_at_5"]:
            base[name] = ""
    else:
        base.update(
            {
                "hit_at_1": int(hit_at_k(expected_set, selected_doc_ids, 1)),
                "hit_at_3": int(hit_at_k(expected_set, selected_doc_ids, 3)),
                "hit_at_5": int(hit_at_k(expected_set, selected_doc_ids, 5)),
                "any_hit_at_1": int(multi_any_hit_at_k(expected_set, selected_doc_ids, 1)),
                "any_hit_at_3": int(multi_any_hit_at_k(expected_set, selected_doc_ids, 3)),
                "any_hit_at_5": int(multi_any_hit_at_k(expected_set, selected_doc_ids, 5)),
                "all_hit_at_1": int(multi_all_hit_at_k(expected_set, selected_doc_ids, 1)),
                "all_hit_at_3": int(multi_all_hit_at_k(expected_set, selected_doc_ids, 3)),
                "all_hit_at_5": int(multi_all_hit_at_k(expected_set, selected_doc_ids, 5)),
            }
        )
    return base


def metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    in_scope = [row for row in rows if row["ground_truth_type"] != "out_of_scope"]
    return {
        "count": len(in_scope),
        "hit_at_1_count": sum(int(row["hit_at_1"]) for row in in_scope),
        "hit_at_1": mean([float(row["hit_at_1"]) for row in in_scope]),
        "hit_at_3_count": sum(int(row["hit_at_3"]) for row in in_scope),
        "hit_at_3": mean([float(row["hit_at_3"]) for row in in_scope]),
        "hit_at_5_count": sum(int(row["hit_at_5"]) for row in in_scope),
        "hit_at_5": mean([float(row["hit_at_5"]) for row in in_scope]),
        "mrr": mean([float(row["reciprocal_rank"]) for row in in_scope]),
    }


def multi_metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    multi = [row for row in rows if row["ground_truth_type"] == "multi"]
    return {
        "count": len(multi),
        "any_hit_at_1_count": sum(int(row["any_hit_at_1"]) for row in multi),
        "any_hit_at_1": mean([float(row["any_hit_at_1"]) for row in multi]),
        "any_hit_at_3_count": sum(int(row["any_hit_at_3"]) for row in multi),
        "any_hit_at_3": mean([float(row["any_hit_at_3"]) for row in multi]),
        "any_hit_at_5_count": sum(int(row["any_hit_at_5"]) for row in multi),
        "any_hit_at_5": mean([float(row["any_hit_at_5"]) for row in multi]),
        "all_hit_at_1_count": sum(int(row["all_hit_at_1"]) for row in multi),
        "all_hit_at_1": mean([float(row["all_hit_at_1"]) for row in multi]),
        "all_hit_at_3_count": sum(int(row["all_hit_at_3"]) for row in multi),
        "all_hit_at_3": mean([float(row["all_hit_at_3"]) for row in multi]),
        "all_hit_at_5_count": sum(int(row["all_hit_at_5"]) for row in multi),
        "all_hit_at_5": mean([float(row["all_hit_at_5"]) for row in multi]),
        "mrr": mean([float(row["reciprocal_rank"]) for row in multi]),
    }


def aggregate_dimensions(rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    output = []
    for variant in ["baseline", "cap2"]:
        scoped_variant = [row for row in rows if row["variant"] == variant and row["ground_truth_type"] != "out_of_scope"]
        values = sorted(set(row[dimension] for row in scoped_variant))
        for value in values:
            scoped = [row for row in scoped_variant if row[dimension] == value]
            summary = metric_summary(scoped)
            output.append({"variant": variant, dimension: value, **summary})
    return output


def latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": mean(values),
        "median_ms": statistics.median(values) if values else 0.0,
        "p95_ms": percentile(values, 0.95),
    }


def summarize_variant(variant_rows: list[dict[str, Any]], query_latencies: list[float], postprocess_latencies: list[float]) -> dict[str, Any]:
    overall = metric_summary(variant_rows)
    single = metric_summary([row for row in variant_rows if row["ground_truth_type"] == "single"])
    multi = multi_metric_summary(variant_rows)
    return {
        **overall,
        "single_count": single["count"],
        "single_hit_at_1_count": single["hit_at_1_count"],
        "single_hit_at_1": single["hit_at_1"],
        "single_hit_at_3_count": single["hit_at_3_count"],
        "single_hit_at_3": single["hit_at_3"],
        "single_hit_at_5_count": single["hit_at_5_count"],
        "single_hit_at_5": single["hit_at_5"],
        "single_mrr": single["mrr"],
        "multi_count": multi["count"],
        "multi_any_hit_at_1_count": multi["any_hit_at_1_count"],
        "multi_any_hit_at_1": multi["any_hit_at_1"],
        "multi_any_hit_at_3_count": multi["any_hit_at_3_count"],
        "multi_any_hit_at_3": multi["any_hit_at_3"],
        "multi_any_hit_at_5_count": multi["any_hit_at_5_count"],
        "multi_any_hit_at_5": multi["any_hit_at_5"],
        "multi_all_hit_at_1_count": multi["all_hit_at_1_count"],
        "multi_all_hit_at_1": multi["all_hit_at_1"],
        "multi_all_hit_at_3_count": multi["all_hit_at_3_count"],
        "multi_all_hit_at_3": multi["all_hit_at_3"],
        "multi_all_hit_at_5_count": multi["all_hit_at_5_count"],
        "multi_all_hit_at_5": multi["all_hit_at_5"],
        "multi_mrr": multi["mrr"],
        "avg_unique_doc_count": mean([float(row["unique_doc_count"]) for row in variant_rows]),
        "avg_duplicate_chunk_count": mean([float(row["duplicate_chunk_count"]) for row in variant_rows]),
        "avg_duplicate_ratio": mean([float(row["duplicate_ratio"]) for row in variant_rows]),
        "max_same_document_occupancy": max(int(row["max_same_document_occupancy"]) for row in variant_rows),
        "avg_context_characters": mean([float(row["context_character_count"]) for row in variant_rows]),
        "avg_approximate_tokens": mean([float(row["approximate_token_count"]) for row in variant_rows]),
        "query_latency": latency_summary(query_latencies),
        "postprocess_latency": latency_summary(postprocess_latencies),
    }


def main() -> int:
    load_dotenv_file(PROJECT_ROOT / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required but will not be printed")
    settings = Settings.from_env()
    manifest = load_manifest(settings.manifest_path)
    provider_by_doc_id = {doc.doc_id: doc.provider for doc in manifest}
    dev_rows = read_csv(DEV_EVALUATION_PATH)
    full_by_id = {row["id"]: row for row in read_csv(FULL_EVALUATION_PATH)}

    embedder = OpenAIEmbedder(model=FROZEN_EMBEDDING_MODEL, api_key=api_key)
    store = ChromaVectorStore(settings.chroma_persist_dir, FROZEN_EVALUATION_CHROMA_COLLECTION)

    per_question: list[dict[str, Any]] = []
    multi_rows: list[dict[str, Any]] = []
    hard_case_rows: list[dict[str, Any]] = []
    query_latencies: list[float] = []
    cap_latencies: list[float] = []

    retrieved_cache: dict[str, list[RetrievedChunk]] = {}
    baseline_by_id: dict[str, dict[str, Any]] = {}
    cap_by_id: dict[str, dict[str, Any]] = {}

    for row in dev_rows:
        started = time.perf_counter()
        raw = store.retrieve(row["question"], embedder, RAW_RETRIEVAL_DEPTH)
        query_latency = (time.perf_counter() - started) * 1000
        query_latencies.append(query_latency)
        retrieved_cache[row["id"]] = raw
        baseline = raw[:FINAL_TOP_K]
        cap_started = time.perf_counter()
        cap = select_with_per_document_cap(raw, top_k=FINAL_TOP_K, per_document_cap=PER_DOCUMENT_CAP)
        cap_latency = (time.perf_counter() - cap_started) * 1000
        cap_latencies.append(cap_latency)
        provider = provider_for_row(row, provider_by_doc_id)
        baseline_row = result_for_variant(row, baseline, "baseline", query_latency, provider)
        cap_row = result_for_variant(row, cap, "cap2", query_latency + cap_latency, provider)
        per_question.extend([baseline_row, cap_row])
        baseline_by_id[row["id"]] = baseline_row
        cap_by_id[row["id"]] = cap_row
        if row["ground_truth_type"] == "multi":
            expected = expected_docs(row)
            raw_doc_ids = [chunk.doc_id for chunk in raw]
            multi_rows.append(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "expected_documents": "|".join(expected),
                    "baseline_retrieved_docs": baseline_row["retrieved_doc_ids"],
                    "cap2_retrieved_docs": cap_row["retrieved_doc_ids"],
                    "baseline_any_hit_at_5": baseline_row["any_hit_at_5"],
                    "cap2_any_hit_at_5": cap_row["any_hit_at_5"],
                    "baseline_all_hit_at_5": baseline_row["all_hit_at_5"],
                    "cap2_all_hit_at_5": cap_row["all_hit_at_5"],
                    "baseline_missing_expected_source_first_rank_in_raw_depth": first_missing_rank(expected, baseline_row["retrieved_doc_ids"].split("|"), raw_doc_ids),
                    "cap2_missing_expected_source_first_rank_in_raw_depth": first_missing_rank(expected, cap_row["retrieved_doc_ids"].split("|"), raw_doc_ids),
                }
            )

    for question_id in sorted(HARD_CASE_IDS):
        row = full_by_id.get(question_id)
        if not row:
            continue
        started = time.perf_counter()
        raw = store.retrieve(row["question"], embedder, RAW_RETRIEVAL_DEPTH)
        query_latency = (time.perf_counter() - started) * 1000
        cap_started = time.perf_counter()
        cap = select_with_per_document_cap(raw, top_k=FINAL_TOP_K, per_document_cap=PER_DOCUMENT_CAP)
        cap_latency = (time.perf_counter() - cap_started) * 1000
        expected = expected_docs(row)
        hard_case_rows.append(
            {
                "id": row["id"],
                "question": row["question"],
                "question_type": row["question_type"],
                "ground_truth_type": row["ground_truth_type"],
                "expected_documents": "|".join(expected),
                "baseline_ranked_docs": doc_list(raw[:FINAL_TOP_K]),
                "cap2_ranked_docs": doc_list(cap),
                "baseline_ranked_chunks": chunk_list(raw[:FINAL_TOP_K]),
                "cap2_ranked_chunks": chunk_list(cap),
                "baseline_any_hit_at_5": "" if row["ground_truth_type"] == "out_of_scope" else int(multi_any_hit_at_k(set(expected), [c.doc_id for c in raw[:FINAL_TOP_K]], 5)),
                "cap2_any_hit_at_5": "" if row["ground_truth_type"] == "out_of_scope" else int(multi_any_hit_at_k(set(expected), [c.doc_id for c in cap], 5)),
                "baseline_all_hit_at_5": "" if row["ground_truth_type"] == "out_of_scope" else int(multi_all_hit_at_k(set(expected), [c.doc_id for c in raw[:FINAL_TOP_K]], 5)),
                "cap2_all_hit_at_5": "" if row["ground_truth_type"] == "out_of_scope" else int(multi_all_hit_at_k(set(expected), [c.doc_id for c in cap], 5)),
                "query_latency_ms": round(query_latency, 3),
                "cap_postprocess_latency_ms": round(cap_latency, 6),
            }
        )

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    per_fields = list(per_question[0].keys())
    write_csv(RESULT_DIR / "diversification_per_question.csv", per_question, per_fields)
    write_csv(RESULT_DIR / "diversification_multi_document.csv", multi_rows, list(multi_rows[0].keys()))
    write_csv(RESULT_DIR / "diversification_hard_cases.csv", hard_case_rows, list(hard_case_rows[0].keys()))

    summary_rows: list[dict[str, Any]] = []
    summary_by_variant: dict[str, dict[str, Any]] = {}
    for variant in ["baseline", "cap2"]:
        scoped = [row for row in per_question if row["variant"] == variant]
        variant_summary = summarize_variant(scoped, query_latencies, cap_latencies if variant == "cap2" else [0.0 for _ in cap_latencies])
        summary_by_variant[variant] = variant_summary
        flat = {"variant": variant, **{k: json.dumps(v) if isinstance(v, dict) else v for k, v in variant_summary.items()}}
        summary_rows.append(flat)
    write_csv(RESULT_DIR / "diversification_summary.csv", summary_rows, list(summary_rows[0].keys()))

    diversity_rows = [
        {
            "variant": variant,
            "average_unique_doc_count": summary_by_variant[variant]["avg_unique_doc_count"],
            "average_duplicate_chunk_count": summary_by_variant[variant]["avg_duplicate_chunk_count"],
            "average_duplicate_ratio": summary_by_variant[variant]["avg_duplicate_ratio"],
            "max_same_document_occupancy": summary_by_variant[variant]["max_same_document_occupancy"],
        }
        for variant in ["baseline", "cap2"]
    ]
    write_csv(RESULT_DIR / "diversification_document_diversity.csv", diversity_rows, list(diversity_rows[0].keys()))

    context_rows = [
        {
            "variant": variant,
            "average_context_characters": summary_by_variant[variant]["avg_context_characters"],
            "average_approximate_tokens": summary_by_variant[variant]["avg_approximate_tokens"],
        }
        for variant in ["baseline", "cap2"]
    ]
    write_csv(RESULT_DIR / "diversification_context.csv", context_rows, list(context_rows[0].keys()))

    provider_rows = aggregate_dimensions(per_question, "provider")
    write_csv(RESULT_DIR / "diversification_by_provider.csv", provider_rows, list(provider_rows[0].keys()))
    question_type_rows = aggregate_dimensions(per_question, "question_type")
    write_csv(RESULT_DIR / "diversification_by_question_type.csv", question_type_rows, list(question_type_rows[0].keys()))

    improved = []
    regressed = []
    for row in dev_rows:
        if row["ground_truth_type"] == "out_of_scope":
            continue
        baseline_hit = int(baseline_by_id[row["id"]]["hit_at_5"])
        cap_hit = int(cap_by_id[row["id"]]["hit_at_5"])
        baseline_rr = float(baseline_by_id[row["id"]]["reciprocal_rank"])
        cap_rr = float(cap_by_id[row["id"]]["reciprocal_rank"])
        if cap_hit > baseline_hit or cap_rr > baseline_rr:
            improved.append(row["id"])
        if cap_hit < baseline_hit or cap_rr < baseline_rr:
            regressed.append(row["id"])

    json_summary = {
        "experiment": "retrieval_diversification_per_document_cap_2",
        "dataset": str(DEV_EVALUATION_PATH.relative_to(PROJECT_ROOT)),
        "held_out_used": False,
        "raw_retrieval_depth": RAW_RETRIEVAL_DEPTH,
        "final_top_k": FINAL_TOP_K,
        "per_document_cap": PER_DOCUMENT_CAP,
        "controlled_variables": {
            "chunk_size": FROZEN_CHUNK_SIZE,
            "chunk_overlap": FROZEN_CHUNK_OVERLAP,
            "chunk_unit": FROZEN_CHUNK_UNIT,
            "embedding_model": FROZEN_EMBEDDING_MODEL,
            "vector_db": "Chroma",
            "collection": FROZEN_EVALUATION_CHROMA_COLLECTION,
            "threshold": FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
            "generation_model": "not_used",
            "judge_model": "not_used",
        },
        "summary": summary_by_variant,
        "multi_all_hit_change": {
            "baseline_count": summary_by_variant["baseline"]["multi_all_hit_at_5_count"],
            "cap2_count": summary_by_variant["cap2"]["multi_all_hit_at_5_count"],
        },
        "improved_questions": improved,
        "regressed_questions": regressed,
        "llm_generation_calls": 0,
        "judge_calls": 0,
        "decision": "candidate_only_not_applied_to_production",
    }
    (RESULT_DIR / "diversification_summary.json").write_text(json.dumps(json_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"dataset": "dev", "held_out_used": False, "raw_depth": RAW_RETRIEVAL_DEPTH, "top_k": FINAL_TOP_K, "cap": PER_DOCUMENT_CAP}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
