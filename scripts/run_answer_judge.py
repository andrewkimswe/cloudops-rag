#!/usr/bin/env python3
"""Run LLM judge diagnostics for existing answer-evaluation generations."""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from openai import OpenAI

from cloudops_rag.api.config import FROZEN_CHROMA_COLLECTION
from cloudops_rag.config.settings import Settings, load_dotenv_file
from cloudops_rag.evaluation.answer_evaluation import load_answer_eval_rubric
from cloudops_rag.evaluation.answer_judge import (
    SCORE_FIELDS,
    aggregate_score_distribution,
    needs_human_review,
    parse_json_object,
    validate_claim_output,
    validate_judge_output,
)
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore

JUDGE_MODEL = "gpt-4.1-mini"
JUDGE_TEMPERATURE = 0
CLAIM_CANDIDATE_IDS = {"ans_eval_001", "ans_eval_007", "ans_eval_009", "ans_eval_010", "ans_eval_011"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writable = row.copy()
            for key, value in list(writable.items()):
                if isinstance(value, (list, dict)):
                    writable[key] = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, bool):
                    writable[key] = str(value).lower()
            writer.writerow(writable)


def json_list(value: str) -> list[str]:
    if not value:
        return []
    return json.loads(value)


def context_for_chunk_ids(store: ChromaVectorStore, chunk_ids: list[str]) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    result = store.collection.get(ids=chunk_ids, include=["documents", "metadatas"])
    docs_by_id = {}
    for chunk_id, text, metadata in zip(result.get("ids", []), result.get("documents", []), result.get("metadatas", [])):
        docs_by_id[chunk_id] = {"chunk_id": chunk_id, "text": text, "metadata": metadata}
    ordered = []
    for chunk_id in chunk_ids:
        item = docs_by_id.get(chunk_id)
        if not item:
            continue
        metadata = item["metadata"] or {}
        ordered.append(
            {
                "chunk_id": chunk_id,
                "doc_id": metadata.get("doc_id", ""),
                "title": metadata.get("title", ""),
                "source_url": metadata.get("source_url", ""),
                "text": item["text"],
            }
        )
    return ordered


def compact_context(chunks: list[dict[str, Any]]) -> str:
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk["text"])
        if len(text) > 2400:
            text = text[:2400] + "\n[truncated]"
        blocks.append(
            f"[rank={index} doc_id={chunk['doc_id']} title={chunk['title']} chunk_id={chunk['chunk_id']}]\n{text}"
        )
    return "\n\n---\n\n".join(blocks)


def answer_judge_prompt(rubric: Any, generation: dict[str, str], chunks: list[dict[str, Any]]) -> str:
    returned_sources = [
        {"doc_id": chunk["doc_id"], "title": chunk["title"], "source_url": chunk["source_url"], "chunk_id": chunk["chunk_id"]}
        for chunk in chunks
        if chunk["doc_id"] in set(json_list(generation["source_doc_ids"]))
    ]
    payload = {
        "question": rubric.question,
        "reference_answer_summary": rubric.reference_answer_summary,
        "required_points": rubric.required_points,
        "allowed_variations": rubric.allowed_variations,
        "disallowed_claims": rubric.disallowed_claims,
        "expected_source_doc_ids": rubric.expected_source_doc_ids,
        "generated_answer": generation["answer"],
        "returned_source_metadata": returned_sources,
        "retrieved_context": compact_context(chunks),
    }
    return (
        "Evaluate the generated answer using only the reference rubric and retrieved context supplied below. "
        "Do not use outside knowledge. Do not evaluate fluency or style.\n\n"
        "Scoring: correctness_score 0=incorrect 1=partial 2=correct; "
        "completeness_score 0=major missing 1=partial 2=sufficient; "
        "faithfulness_score 0=material unsupported/contradicted 1=mostly grounded 2=sufficiently grounded; "
        "source_support_score 0=sources do not support core answer 1=partial 2=support core answer.\n\n"
        "Classify overall_failure_type as retrieval_failure, generation_failure, combined_failure, or no_material_failure. "
        "Retrieval failure means needed evidence source/context is missing. Generation failure means evidence was present but the answer was wrong or incomplete.\n\n"
        "Return only JSON with keys: correctness_score, correctness_reason, completeness_score, missing_required_points, "
        "faithfulness_score, unsupported_claims, contradicted_claims, source_support_score, source_support_reason, "
        "overall_failure_type, judge_confidence.\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def claim_judge_prompt(rubric: Any, generation: dict[str, str], chunks: list[dict[str, Any]]) -> str:
    payload = {
        "question": rubric.question,
        "reference_answer_summary": rubric.reference_answer_summary,
        "required_points": rubric.required_points,
        "generated_answer": generation["answer"],
        "retrieved_context": compact_context(chunks),
    }
    return (
        "Break the generated answer into factual CloudOps claims and judge each claim using only the supplied retrieved context. "
        "If a claim is true in general but not supported by the supplied context, mark it unsupported or unclear. "
        "Return 3 to 8 material factual claims, not style comments.\n\n"
        "Return only JSON: {\"claims\": [{\"claim_id\": \"c1\", \"claim_text\": \"...\", "
        "\"support_status\": \"supported|unsupported|contradicted|unclear\", \"supporting_doc_ids\": [], "
        "\"supporting_chunk_ids\": [], \"reason\": \"short reason\"}]}\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def call_json(client: OpenAI, prompt: str) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": "You are a strict JSON-only evaluator for RAG answer quality."},
            {"role": "user", "content": prompt},
        ],
        temperature=JUDGE_TEMPERATURE,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return parse_json_object(content)



def final_failure_type(judge_payload: dict[str, Any], missing_source_doc_ids: list[str]) -> str:
    unsupported = judge_payload["unsupported_claims"]
    contradicted = judge_payload["contradicted_claims"]
    if all(int(judge_payload[field]) == 2 for field in ["correctness_score", "completeness_score", "faithfulness_score", "source_support_score"]):
        return "no_material_failure"
    if missing_source_doc_ids and (unsupported or contradicted):
        return "combined_failure"
    if missing_source_doc_ids:
        return "retrieval_failure"
    return "generation_failure"


def review_reason(judge_row: dict[str, Any], deterministic_row: dict[str, str]) -> list[str]:
    reasons = []
    if judge_row["judge_confidence"] == "low":
        reasons.append("low_confidence")
    if any(int(judge_row[field]) < 2 for field in SCORE_FIELDS):
        reasons.append("metric_below_2")
    if judge_row["question_type"] == "multi-document":
        reasons.append("multi_document")
    if json.loads(judge_row["unsupported_claims"]):
        reasons.append("unsupported_claim")
    if deterministic_row.get("failure_category") in {"missing_expected_source", "partial_multi_document_sources"}:
        reasons.append(deterministic_row["failure_category"])
    return reasons


def main() -> int:
    load_dotenv_file(PROJECT_ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required but will not be printed")

    output_dir = PROJECT_ROOT / "results" / "answer_evaluation"
    rubric_rows = load_answer_eval_rubric(PROJECT_ROOT / "data" / "answer_evaluation" / "answer_eval_diagnostic.csv")
    rubric_by_id = {row.eval_id: row for row in rubric_rows}
    generation_rows = read_csv(output_dir / "answer_eval_generation.csv")
    deterministic_rows = {row["eval_id"]: row for row in read_csv(output_dir / "answer_eval_deterministic_metrics.csv")}
    generated_rows = [row for row in generation_rows if row["fallback"].lower() == "false"]

    settings = Settings.from_env()
    store = ChromaVectorStore(settings.chroma_persist_dir, FROZEN_CHROMA_COLLECTION)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    run_id = datetime.now(UTC).strftime("answer_judge_%Y%m%dT%H%M%SZ")

    judge_rows: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    human_rows: list[dict[str, Any]] = []
    answer_judge_calls = 0
    claim_judge_calls = 0

    for generation in generated_rows:
        rubric = rubric_by_id[generation["eval_id"]]
        chunks = context_for_chunk_ids(store, json_list(generation["retrieved_chunk_ids"]))
        judge_payload = validate_judge_output(call_json(client, answer_judge_prompt(rubric, generation, chunks)))
        answer_judge_calls += 1
        judge_row = {
            "run_id": run_id,
            "eval_id": rubric.eval_id,
            "source_eval_id": rubric.source_eval_id,
            "question_type": rubric.question_type,
            "ground_truth_type": rubric.ground_truth_type,
            "expected_source_doc_ids": rubric.expected_source_doc_ids,
            "returned_source_doc_ids": json_list(generation["source_doc_ids"]),
            "top_1_distance": generation["top_1_distance"],
            "judge_model": JUDGE_MODEL,
            "judge_temperature": JUDGE_TEMPERATURE,
            **judge_payload,
        }
        judge_rows.append(judge_row)
        reasons = review_reason({**judge_row, "unsupported_claims": json.dumps(judge_row["unsupported_claims"])}, deterministic_rows[rubric.eval_id])
        human_rows.append(
            {
                "run_id": run_id,
                "eval_id": rubric.eval_id,
                "source_eval_id": rubric.source_eval_id,
                "question_type": rubric.question_type,
                "needs_human_review": bool(reasons),
                "review_reason": reasons,
                "human_review_status": "pending",
                "human_agrees_with_judge": "",
                "human_correctness": "",
                "human_completeness": "",
                "human_faithfulness": "",
                "human_source_support": "",
                "human_notes": "",
            }
        )
        missing_source_doc_ids = [doc_id for doc_id in rubric.expected_source_doc_ids if doc_id not in set(json_list(generation["source_doc_ids"]))]
        failure_rows.append(
            {
                "run_id": run_id,
                "eval_id": rubric.eval_id,
                "source_eval_id": rubric.source_eval_id,
                "question_type": rubric.question_type,
                "expected_source_doc_ids": rubric.expected_source_doc_ids,
                "returned_source_doc_ids": json_list(generation["source_doc_ids"]),
                "missing_source_doc_ids": missing_source_doc_ids,
                "missing_required_points": judge_payload["missing_required_points"],
                "unsupported_claims": judge_payload["unsupported_claims"],
                "contradicted_claims": judge_payload["contradicted_claims"],
                "judge_overall_failure_type": judge_payload["overall_failure_type"],
                "final_failure_type": final_failure_type(judge_payload, missing_source_doc_ids),
                "judge_confidence": judge_payload["judge_confidence"],
                "deterministic_failure_category": deterministic_rows[rubric.eval_id]["failure_category"],
                "analysis_note": judge_payload["correctness_reason"],
            }
        )
        if rubric.eval_id in CLAIM_CANDIDATE_IDS:
            claims = validate_claim_output(call_json(client, claim_judge_prompt(rubric, generation, chunks)))
            claim_judge_calls += 1
            for claim in claims:
                claim_rows.append(
                    {
                        "run_id": run_id,
                        "eval_id": rubric.eval_id,
                        "source_eval_id": rubric.source_eval_id,
                        **claim,
                    }
                )

    for generation in generation_rows:
        if generation["fallback"].lower() == "true":
            rubric = rubric_by_id[generation["eval_id"]]
            human_rows.append(
                {
                    "run_id": run_id,
                    "eval_id": rubric.eval_id,
                    "source_eval_id": rubric.source_eval_id,
                    "question_type": rubric.question_type,
                    "needs_human_review": False,
                    "review_reason": ["correct_fallback_generation_skipped"],
                    "human_review_status": "pending",
                    "human_agrees_with_judge": "",
                    "human_correctness": "",
                    "human_completeness": "",
                    "human_faithfulness": "",
                    "human_source_support": "",
                    "human_notes": "",
                }
            )

    judge_fieldnames = [
        "run_id", "eval_id", "source_eval_id", "question_type", "ground_truth_type", "expected_source_doc_ids",
        "returned_source_doc_ids", "top_1_distance", "judge_model", "judge_temperature", "correctness_score",
        "correctness_reason", "completeness_score", "missing_required_points", "faithfulness_score",
        "unsupported_claims", "contradicted_claims", "source_support_score", "source_support_reason",
        "overall_failure_type", "judge_confidence",
    ]
    claim_fieldnames = [
        "run_id", "eval_id", "source_eval_id", "claim_id", "claim_text", "support_status",
        "supporting_doc_ids", "supporting_chunk_ids", "reason",
    ]
    failure_fieldnames = [
        "run_id", "eval_id", "source_eval_id", "question_type", "expected_source_doc_ids", "returned_source_doc_ids",
        "missing_source_doc_ids", "missing_required_points", "unsupported_claims", "contradicted_claims",
        "judge_overall_failure_type", "final_failure_type", "judge_confidence", "deterministic_failure_category", "analysis_note",
    ]
    human_fieldnames = [
        "run_id", "eval_id", "source_eval_id", "question_type", "needs_human_review", "review_reason",
        "human_review_status", "human_agrees_with_judge", "human_correctness", "human_completeness",
        "human_faithfulness", "human_source_support", "human_notes",
    ]
    write_csv(output_dir / "answer_eval_judge.csv", judge_fieldnames, judge_rows)
    write_csv(output_dir / "answer_eval_claims.csv", claim_fieldnames, claim_rows)
    write_csv(output_dir / "answer_eval_failures.csv", failure_fieldnames, failure_rows)
    write_csv(output_dir / "answer_eval_human_review.csv", human_fieldnames, human_rows)

    score_summary = aggregate_score_distribution(judge_rows)
    claim_counts: dict[str, int] = {"supported": 0, "unsupported": 0, "contradicted": 0, "unclear": 0}
    for row in claim_rows:
        claim_counts[row["support_status"]] += 1
    failure_counts: dict[str, int] = {
        "retrieval_failure": 0,
        "generation_failure": 0,
        "combined_failure": 0,
        "no_material_failure": 0,
    }
    for row in failure_rows:
        failure_counts[row["final_failure_type"]] += 1
    fallback_rows = [row for row in deterministic_rows.values() if row["expected_fallback"] == "True"]
    summary = {
        "run_id": run_id,
        "judge_model": JUDGE_MODEL,
        "judge_temperature": JUDGE_TEMPERATURE,
        "answer_judge_calls": answer_judge_calls,
        "claim_level_judge_calls": claim_judge_calls,
        "evaluated_generated_answers": len(generated_rows),
        "fallback_rows": len(fallback_rows),
        "fallback_correct_count": sum(row["fallback_correct"] == "True" for row in fallback_rows),
        "score_distribution": score_summary,
        "claim_support_counts": claim_counts,
        "failure_type_counts": failure_counts,
        "human_review_pending_count": sum(1 for row in human_rows if row["needs_human_review"]),
        "outputs": {
            "judge": "results/answer_evaluation/answer_eval_judge.csv",
            "claims": "results/answer_evaluation/answer_eval_claims.csv",
            "failures": "results/answer_evaluation/answer_eval_failures.csv",
            "human_review": "results/answer_evaluation/answer_eval_human_review.csv",
        },
        "notes": [
            "Judge output is diagnostic evidence, not absolute ground truth.",
            "Generated answer snapshot was reused and not regenerated.",
            "Out-of-scope fallback rows are summarized separately from generated answer scores.",
        ],
    }
    (output_dir / "answer_eval_final_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "answer_judge_calls": answer_judge_calls, "claim_level_judge_calls": claim_judge_calls}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
