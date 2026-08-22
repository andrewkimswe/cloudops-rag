#!/usr/bin/env python3
"""Run Phase 12 distance threshold and fallback analysis on the dev set only."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.config.settings import Settings
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.generation.openai_llm import OpenAILLM
from cloudops_rag.generation.rag_service import RagService
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore
from cloudops_rag.retrieval.schemas import RetrievedChunk


DEV_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_dev.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "threshold"

COLLECTION_NAME = "cloudops_rag_v1_embedding_openai_text_embedding_3_small"
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"
TOP_K = 5
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128
CHUNK_UNIT = "character"
TRACKED_FAILURE_IDS = {"eval_002", "eval_007", "eval_027"}


class CountingLLM:
    def __init__(self, llm: OpenAILLM):
        self.llm = llm
        self.calls = 0

    def answer(self, question: str, retrieved_chunks: list[RetrievedChunk]) -> str:
        self.calls += 1
        return self.llm.answer(question, retrieved_chunks)


def read_dev_rows() -> list[dict[str, str]]:
    with DEV_EVALUATION_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * percentile_value
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def describe(values: list[float], label: str) -> dict[str, Any]:
    sorted_values = sorted(values)
    return {
        "scope": label,
        "count": len(values),
        "min": min(sorted_values),
        "max": max(sorted_values),
        "mean": statistics.mean(sorted_values),
        "median": statistics.median(sorted_values),
        "p10": percentile(sorted_values, 0.10),
        "p25": percentile(sorted_values, 0.25),
        "p75": percentile(sorted_values, 0.75),
        "p90": percentile(sorted_values, 0.90),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def doc_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join(chunk.doc_id for chunk in chunks)


def score_list(chunks: list[RetrievedChunk]) -> str:
    return "|".join("" if chunk.score is None else f"{chunk.score:.6f}" for chunk in chunks)


def collect_scores(rows: list[dict[str, str]], store: ChromaVectorStore, embedder: OpenAIEmbedder) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        retrieved = store.retrieve(row["question"], embedder, top_k=TOP_K)
        rank_1 = retrieved[0]
        output.append(
            {
                "id": row["id"],
                "question": row["question"],
                "ground_truth_type": row["ground_truth_type"],
                "question_type": row["question_type"],
                "scope": "out_of_scope" if row["ground_truth_type"] == "out_of_scope" else "in_scope",
                "expected_document_1": row["expected_document_1"],
                "expected_document_2": row["expected_document_2"],
                "top_1_doc_id": rank_1.doc_id,
                "top_1_title": rank_1.title,
                "top_1_distance": float(rank_1.score),
                "top_3_doc_ids": doc_list(retrieved[:3]),
                "top_5_doc_ids": doc_list(retrieved[:5]),
                "top_5_distances": score_list(retrieved[:5]),
            }
        )
    return output


def candidate_thresholds(score_rows: list[dict[str, Any]]) -> list[float]:
    in_scores = sorted(row["top_1_distance"] for row in score_rows if row["scope"] == "in_scope")
    out_scores = sorted(row["top_1_distance"] for row in score_rows if row["scope"] == "out_of_scope")
    candidates = {
        percentile(in_scores, 0.75),
        percentile(in_scores, 0.90),
        percentile(in_scores, 0.95),
        max(in_scores),
        (max(in_scores) + min(out_scores)) / 2,
        min(out_scores),
        percentile(out_scores, 0.25),
        statistics.median(out_scores),
        percentile(out_scores, 0.75),
    }
    return sorted(round(value, 6) for value in candidates)


def evaluate_threshold(score_rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    in_scope = [row for row in score_rows if row["scope"] == "in_scope"]
    out_scope = [row for row in score_rows if row["scope"] == "out_of_scope"]
    accepted = [row for row in score_rows if row["top_1_distance"] <= threshold]
    rejected = [row for row in score_rows if row["top_1_distance"] > threshold]
    ta = sum(row["scope"] == "in_scope" for row in accepted)
    fr = sum(row["scope"] == "in_scope" for row in rejected)
    tr = sum(row["scope"] == "out_of_scope" for row in rejected)
    fa = sum(row["scope"] == "out_of_scope" for row in accepted)
    return {
        "threshold": threshold,
        "threshold_rule": "accept_if_top_1_l2_distance_lte_threshold",
        "true_accept": ta,
        "false_reject": fr,
        "true_reject": tr,
        "false_accept": fa,
        "in_scope_total": len(in_scope),
        "out_of_scope_total": len(out_scope),
        "in_scope_acceptance_rate": ta / len(in_scope),
        "out_of_scope_rejection_rate": tr / len(out_scope),
        "false_reject_rate": fr / len(in_scope),
        "false_accept_rate": fa / len(out_scope),
        "accept_precision": ta / len(accepted) if accepted else 0.0,
        "reject_precision": tr / len(rejected) if rejected else 0.0,
    }


def select_threshold(candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    zero_fa = [row for row in candidate_rows if row["false_accept"] == 0]
    if zero_fa:
        max_true_accept = max(row["true_accept"] for row in zero_fa)
        best_acceptance = [row for row in zero_fa if row["true_accept"] == max_true_accept]
        return min(best_acceptance, key=lambda row: row["threshold"])
    return min(candidate_rows, key=lambda row: (row["false_accept"], row["false_reject"], -row["true_accept"]))


def classify_rows(score_rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in score_rows:
        accept = row["top_1_distance"] <= threshold
        if row["scope"] == "in_scope" and accept:
            classification = "TA"
        elif row["scope"] == "in_scope":
            classification = "FR"
        elif accept:
            classification = "FA"
        else:
            classification = "TR"
        output.append(
            {
                **row,
                "selected_threshold": threshold,
                "decision": "accept" if accept else "reject",
                "classification": classification,
                "distance_margin": row["top_1_distance"] - threshold,
            }
        )
    return output


def borderline_rows(classified_rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    enriched = [{**row, "absolute_margin": abs(row["top_1_distance"] - threshold)} for row in classified_rows]
    selected: list[dict[str, Any]] = []
    selected.extend(sorted([row for row in enriched if row["scope"] == "in_scope"], key=lambda row: row["absolute_margin"])[:3])
    selected.extend(sorted([row for row in enriched if row["scope"] == "out_of_scope"], key=lambda row: row["absolute_margin"])[:3])
    selected.extend(sorted([row for row in enriched if row["classification"] == "FA"], key=lambda row: row["absolute_margin"])[:3])
    selected.extend(sorted([row for row in enriched if row["classification"] == "FR"], key=lambda row: row["absolute_margin"])[:3])
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for row in selected:
        key = (row["id"], row["classification"])
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def out_of_scope_observation(row: dict[str, Any], threshold: float) -> str:
    if row["top_1_distance"] <= threshold:
        return "false_accept_risk: unsupported query would reach generation"
    return "rejected: top-1 distance is above selected threshold"


def in_scope_observation(row: dict[str, Any]) -> str:
    if row["id"] in TRACKED_FAILURE_IDS:
        return "tracked semantic failure; threshold cannot verify document correctness"
    if row["classification"] == "FR":
        return "false reject candidate near or above threshold"
    return "accepted by threshold"


def run_smoke_test(
    settings: Settings,
    store: ChromaVectorStore,
    embedder: OpenAIEmbedder,
    threshold: float,
    classified_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    llm = CountingLLM(OpenAILLM(model=LLM_MODEL, api_key=settings.openai_api_key))
    service = RagService(store, embedder, llm, top_k=TOP_K, distance_threshold=threshold)
    cases = [
        {
            "case": "in_scope",
            "id": "eval_001",
            "question": next(row["question"] for row in classified_rows if row["id"] == "eval_001"),
        },
        {
            "case": "out_of_scope",
            "id": "eval_039",
            "question": next(row["question"] for row in classified_rows if row["id"] == "eval_039"),
        },
    ]
    closest = min(classified_rows, key=lambda row: abs(row["top_1_distance"] - threshold))
    cases.append({"case": "borderline", "id": closest["id"], "question": closest["question"]})

    results = []
    for case in cases:
        calls_before = llm.calls
        result = service.query(case["question"])
        calls_after = llm.calls
        results.append(
            {
                "case": case["case"],
                "id": case["id"],
                "fallback": result.fallback,
                "llm_called": calls_after > calls_before,
                "llm_calls_delta": calls_after - calls_before,
                "retrieval_distance": result.retrieval_distance,
                "distance_threshold": result.distance_threshold,
                "source_count": len(result.sources),
                "source_doc_ids": [source.doc_id for source in result.sources],
                "answer_preview": result.answer[:240],
            }
        )
    return {
        "selected_threshold": threshold,
        "llm_total_calls": llm.calls,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_dev_rows()
    embedder = OpenAIEmbedder(model=EMBEDDING_MODEL, api_key=settings.openai_api_key)
    store = ChromaVectorStore(settings.chroma_persist_dir, COLLECTION_NAME)

    score_rows = collect_scores(rows, store, embedder)
    in_scores = [row["top_1_distance"] for row in score_rows if row["scope"] == "in_scope"]
    out_scores = [row["top_1_distance"] for row in score_rows if row["scope"] == "out_of_scope"]
    distribution_summary = [describe(in_scores, "in_scope"), describe(out_scores, "out_of_scope")]
    thresholds = candidate_thresholds(score_rows)
    threshold_rows = [evaluate_threshold(score_rows, threshold) for threshold in thresholds]
    selected = select_threshold(threshold_rows)
    selected_threshold = float(selected["threshold"])
    classified = classify_rows(score_rows, selected_threshold)
    borderline = borderline_rows(classified, selected_threshold)

    out_analysis = [
        {**row, "observation": out_of_scope_observation(row, selected_threshold)}
        for row in classified
        if row["scope"] == "out_of_scope"
    ]
    low_confidence = sorted(
        [
            {**row, "observation": in_scope_observation(row)}
            for row in classified
            if row["scope"] == "in_scope" and (row["classification"] == "FR" or row["id"] in TRACKED_FAILURE_IDS)
        ],
        key=lambda row: row["top_1_distance"],
        reverse=True,
    )

    score_fields = [
        "id",
        "question",
        "ground_truth_type",
        "question_type",
        "scope",
        "expected_document_1",
        "expected_document_2",
        "top_1_doc_id",
        "top_1_title",
        "top_1_distance",
        "top_3_doc_ids",
        "top_5_doc_ids",
        "top_5_distances",
    ]
    classified_fields = score_fields + ["selected_threshold", "decision", "classification", "distance_margin"]
    write_csv(RESULT_DIR / "score_distribution.csv", score_rows, score_fields)
    write_csv(
        RESULT_DIR / "score_distribution_summary.csv",
        distribution_summary,
        ["scope", "count", "min", "max", "mean", "median", "p10", "p25", "p75", "p90"],
    )
    write_csv(
        RESULT_DIR / "threshold_candidates.csv",
        threshold_rows,
        [
            "threshold",
            "threshold_rule",
            "true_accept",
            "false_reject",
            "true_reject",
            "false_accept",
            "in_scope_total",
            "out_of_scope_total",
            "in_scope_acceptance_rate",
            "out_of_scope_rejection_rate",
            "false_reject_rate",
            "false_accept_rate",
            "accept_precision",
            "reject_precision",
        ],
    )
    write_csv(RESULT_DIR / "threshold_per_question.csv", classified, classified_fields)
    write_csv(
        RESULT_DIR / "threshold_confusion_matrix.csv",
        [
            {
                "selected_threshold": selected_threshold,
                "true_accept": selected["true_accept"],
                "false_reject": selected["false_reject"],
                "true_reject": selected["true_reject"],
                "false_accept": selected["false_accept"],
                "in_scope_acceptance_rate": selected["in_scope_acceptance_rate"],
                "out_of_scope_rejection_rate": selected["out_of_scope_rejection_rate"],
                "false_reject_rate": selected["false_reject_rate"],
                "false_accept_rate": selected["false_accept_rate"],
            }
        ],
        [
            "selected_threshold",
            "true_accept",
            "false_reject",
            "true_reject",
            "false_accept",
            "in_scope_acceptance_rate",
            "out_of_scope_rejection_rate",
            "false_reject_rate",
            "false_accept_rate",
        ],
    )
    write_csv(RESULT_DIR / "borderline_questions.csv", borderline, classified_fields + ["absolute_margin"])
    write_csv(RESULT_DIR / "out_of_scope_analysis.csv", out_analysis, classified_fields + ["observation"])
    write_csv(RESULT_DIR / "in_scope_low_confidence.csv", low_confidence, classified_fields + ["observation"])

    smoke_result = None
    if args.smoke_test:
        smoke_result = run_smoke_test(settings, store, embedder, selected_threshold, classified)
        (RESULT_DIR / "fallback_smoke_test.json").write_text(
            json.dumps(smoke_result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    metadata = {
        "phase": "Phase 12",
        "held_out_test_used": False,
        "dataset": str(DEV_EVALUATION_PATH.relative_to(PROJECT_ROOT)),
        "frozen_retrieval_configuration": {
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "chunk_unit": CHUNK_UNIT,
            "embedding_model": EMBEDDING_MODEL,
            "vector_db": "Chroma",
            "retrieval_top_k": TOP_K,
            "collection": COLLECTION_NAME,
        },
        "score_semantics": {
            "returned_field": "distances",
            "metric": "l2",
            "direction": "smaller_is_more_similar",
            "accept_rule": "top_1_l2_distance <= selected_threshold",
        },
        "threshold_signal": "top_1_retrieved_chunk_l2_distance",
        "selected_threshold": selected_threshold,
        "selected_confusion_matrix": selected,
        "smoke_test_run": args.smoke_test,
        "smoke_test": smoke_result,
    }
    (RESULT_DIR / "threshold_summary.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
