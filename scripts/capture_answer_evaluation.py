#!/usr/bin/env python3
"""Capture answer-evaluation diagnostic generations and deterministic checks."""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.api.config import (
    DEFAULT_OPENAI_EMBEDDING_TIMEOUT_SECONDS,
    DEFAULT_OPENAI_LLM_TIMEOUT_SECONDS,
    FROZEN_CHROMA_COLLECTION,
    FROZEN_EMBEDDING_MODEL,
    FROZEN_LLM_MODEL,
    FROZEN_RETRIEVAL_TOP_K,
    FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
)
from cloudops_rag.config.settings import Settings, load_dotenv_file
from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.evaluation.answer_evaluation import deterministic_evaluate_row, load_answer_eval_rubric
from cloudops_rag.generation.openai_llm import OpenAILLM
from cloudops_rag.generation.rag_service import deduplicate_sources
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore


def dump_json_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def main() -> int:
    dataset_path = PROJECT_ROOT / "data" / "answer_evaluation" / "answer_eval_diagnostic.csv"
    output_dir = PROJECT_ROOT / "results" / "answer_evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)
    generation_path = output_dir / "answer_eval_generation.csv"
    metrics_path = output_dir / "answer_eval_deterministic_metrics.csv"
    summary_path = output_dir / "answer_eval_summary.json"

    load_dotenv_file(PROJECT_ROOT / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required but will not be printed")

    settings = Settings.from_env()
    embedder = OpenAIEmbedder(
        model=FROZEN_EMBEDDING_MODEL,
        api_key=api_key,
        timeout=DEFAULT_OPENAI_EMBEDDING_TIMEOUT_SECONDS,
    )
    llm = OpenAILLM(
        model=FROZEN_LLM_MODEL,
        api_key=api_key,
        timeout=DEFAULT_OPENAI_LLM_TIMEOUT_SECONDS,
    )
    store = ChromaVectorStore(settings.chroma_persist_dir, FROZEN_CHROMA_COLLECTION)
    rubric_rows = load_answer_eval_rubric(dataset_path)
    run_id = datetime.now(UTC).strftime("answer_eval_%Y%m%dT%H%M%SZ")

    generation_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    llm_generation_calls = 0
    for rubric in rubric_rows:
        retrieval_started = time.perf_counter()
        retrieved = store.retrieve(rubric.question, embedder, FROZEN_RETRIEVAL_TOP_K)
        retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000
        top_1_distance = retrieved[0].score if retrieved else None
        fallback = top_1_distance is None or top_1_distance > FROZEN_TOP_1_L2_DISTANCE_THRESHOLD
        generation_latency_ms = 0.0
        if fallback:
            answer = "I couldn't find sufficient support for this question in the indexed documents."
            sources = []
        else:
            generation_started = time.perf_counter()
            answer = llm.answer(rubric.question, retrieved)
            generation_latency_ms = (time.perf_counter() - generation_started) * 1000
            sources = deduplicate_sources(retrieved)
            llm_generation_calls += 1
        source_doc_ids = [source.doc_id for source in sources]
        retrieved_doc_ids = [chunk.doc_id for chunk in retrieved]
        retrieved_chunk_ids = [chunk.chunk_id for chunk in retrieved]
        generation_row = {
            "run_id": run_id,
            "eval_id": rubric.eval_id,
            "source_eval_id": rubric.source_eval_id,
            "question": rubric.question,
            "question_type": rubric.question_type,
            "ground_truth_type": rubric.ground_truth_type,
            "expected_source_doc_ids": dump_json_list(rubric.expected_source_doc_ids),
            "expected_fallback": str(rubric.expected_fallback).lower(),
            "fallback": fallback,
            "answer": answer,
            "source_doc_ids": source_doc_ids,
            "source_ranks": [source.rank for source in sources],
            "retrieved_doc_ids": retrieved_doc_ids,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "top_1_distance": top_1_distance,
            "retrieval_latency_ms": round(retrieval_latency_ms, 2),
            "generation_latency_ms": round(generation_latency_ms, 2),
            "generation_model": FROZEN_LLM_MODEL,
            "embedding_model": FROZEN_EMBEDDING_MODEL,
            "retrieval_top_k": FROZEN_RETRIEVAL_TOP_K,
            "distance_threshold": FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
            "generation_temperature": 0,
            "claim_analysis_candidate": str(rubric.claim_analysis_candidate).lower(),
            "human_correctness": "",
            "human_completeness": "",
            "human_faithfulness": "",
            "human_source_support": "",
            "human_notes": "",
        }
        generation_rows.append(generation_row)
        metric_input = {
            **generation_row,
            "source_doc_ids": source_doc_ids,
        }
        metric_rows.append(deterministic_evaluate_row(rubric, metric_input))

    generation_fieldnames = [
        "run_id", "eval_id", "source_eval_id", "question", "question_type", "ground_truth_type",
        "expected_source_doc_ids", "expected_fallback", "fallback", "answer", "source_doc_ids",
        "source_ranks", "retrieved_doc_ids", "retrieved_chunk_ids", "top_1_distance",
        "retrieval_latency_ms", "generation_latency_ms", "generation_model", "embedding_model",
        "retrieval_top_k", "distance_threshold", "generation_temperature", "claim_analysis_candidate",
        "human_correctness", "human_completeness", "human_faithfulness", "human_source_support", "human_notes",
    ]
    with generation_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=generation_fieldnames)
        writer.writeheader()
        for row in generation_rows:
            writable = row.copy()
            for key in ("source_doc_ids", "source_ranks", "retrieved_doc_ids", "retrieved_chunk_ids"):
                writable[key] = json.dumps(writable[key], ensure_ascii=False)
            writer.writerow(writable)

    metric_fieldnames = [
        "eval_id", "source_eval_id", "expected_fallback", "actual_fallback", "fallback_correct",
        "empty_missing_answer", "unsupported_generation_on_fallback", "source_hit_count",
        "source_expected_count", "source_any_hit", "source_all_hit", "matched_source_doc_ids",
        "multi_source_all_hit", "failure_category",
    ]
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=metric_fieldnames)
        writer.writeheader()
        for row in metric_rows:
            writable = row.copy()
            writable["matched_source_doc_ids"] = json.dumps(writable["matched_source_doc_ids"], ensure_ascii=False)
            writer.writerow(writable)

    summary = {
        "run_id": run_id,
        "dataset": str(dataset_path.relative_to(PROJECT_ROOT)),
        "generation_output": str(generation_path.relative_to(PROJECT_ROOT)),
        "deterministic_metrics_output": str(metrics_path.relative_to(PROJECT_ROOT)),
        "question_count": len(rubric_rows),
        "llm_generation_calls": llm_generation_calls,
        "llm_judge_calls": 0,
        "generation_model": FROZEN_LLM_MODEL,
        "embedding_model": FROZEN_EMBEDDING_MODEL,
        "retrieval_top_k": FROZEN_RETRIEVAL_TOP_K,
        "distance_threshold": FROZEN_TOP_1_L2_DISTANCE_THRESHOLD,
        "generation_temperature": 0,
        "fallback_correct_count": sum(1 for row in metric_rows if row["fallback_correct"]),
        "source_any_hit_count": sum(1 for row in metric_rows if row["source_any_hit"]),
        "source_all_hit_count": sum(1 for row in metric_rows if row["source_all_hit"]),
        "multi_source_all_hit_count": sum(1 for row in metric_rows if row["multi_source_all_hit"] is True),
        "failure_category_counts": {},
    }
    for row in metric_rows:
        category = str(row["failure_category"])
        summary["failure_category_counts"][category] = summary["failure_category_counts"].get(category, 0) + 1
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "question_count": len(rubric_rows), "llm_generation_calls": llm_generation_calls, "llm_judge_calls": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
