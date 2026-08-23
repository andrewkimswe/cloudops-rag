#!/usr/bin/env python3
"""Build human-review sheet and markdown packet from existing judge outputs."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.api.config import FROZEN_CHROMA_COLLECTION
from cloudops_rag.config.settings import Settings, load_dotenv_file
from cloudops_rag.evaluation.answer_evaluation import load_answer_eval_rubric
from cloudops_rag.retrieval.chroma_store import ChromaVectorStore

OUTPUT_COLUMNS = [
    "eval_id", "source_eval_id", "question", "question_type", "review_priority",
    "priority_reasons", "reference_answer_summary", "required_points", "allowed_variations",
    "disallowed_claims", "generated_answer", "expected_source_doc_ids", "returned_source_doc_ids",
    "retrieved_doc_ids", "top_1_distance", "judge_correctness", "judge_correctness_reason",
    "judge_completeness", "judge_missing_required_points", "judge_faithfulness",
    "judge_unsupported_claims", "judge_contradicted_claims", "judge_source_support",
    "judge_source_support_reason", "judge_failure_type", "judge_confidence", "human_correctness",
    "human_completeness", "human_faithfulness", "human_source_support", "human_agrees_with_judge",
    "human_final_failure_type", "human_notes",
]
HIGH_PRIORITY_IDS = {"ans_eval_007", "ans_eval_009", "ans_eval_010", "ans_eval_011"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def json_list(value: str) -> list[str]:
    return json.loads(value) if value else []


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: dump(row.get(key, "")) for key in OUTPUT_COLUMNS})


def chunk_texts(store: ChromaVectorStore, chunk_ids: list[str]) -> list[dict[str, str]]:
    if not chunk_ids:
        return []
    result = store.collection.get(ids=chunk_ids, include=["documents", "metadatas"])
    found = {}
    for chunk_id, text, metadata in zip(result.get("ids", []), result.get("documents", []), result.get("metadatas", [])):
        metadata = metadata or {}
        found[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": str(metadata.get("doc_id", "")),
            "title": str(metadata.get("title", "")),
            "text": str(text),
        }
    return [found[chunk_id] for chunk_id in chunk_ids if chunk_id in found]


def evidence_excerpt(text: str, limit: int = 900) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ... [excerpt truncated]"


def priority_reasons(eval_id: str, question_type: str, judge: dict[str, str], claims: list[dict[str, str]]) -> list[str]:
    reasons = []
    if eval_id in HIGH_PRIORITY_IDS:
        reasons.append("explicit_high_priority")
    if question_type == "multi-document":
        reasons.append("multi_document")
    if any(int(judge[field]) < 2 for field in ["correctness_score", "completeness_score", "faithfulness_score", "source_support_score"]):
        reasons.append("judge_score_below_2")
    if judge.get("judge_confidence") == "low":
        reasons.append("low_judge_confidence")
    if json_list(judge.get("unsupported_claims", "[]")):
        reasons.append("answer_level_unsupported_claim")
    if json_list(judge.get("contradicted_claims", "[]")):
        reasons.append("answer_level_contradicted_claim")
    if any(row["support_status"] == "unsupported" for row in claims):
        reasons.append("claim_level_unsupported_claim")
    if any(row["support_status"] == "contradicted" for row in claims):
        reasons.append("claim_level_contradicted_claim")
    return reasons


def markdown_list(values: list[str]) -> str:
    if not values:
        return "- None"
    return "\n".join(f"- {value}" for value in values)


def build_packet(rows: list[dict[str, Any]], evidence_by_eval: dict[str, list[dict[str, str]]]) -> str:
    parts = [
        "# Answer Evaluation Human Review Packet",
        "",
        "Use this packet to review generated answers before looking at judge results. Human score fields in the CSV must be filled by the reviewer, not by Codex.",
        "",
    ]
    for row in rows:
        eval_id = row["eval_id"]
        parts.extend([
            "----------------------------------------",
            "",
            f"## {eval_id} / {row['source_eval_id']}",
            "",
            f"Priority: {row['review_priority']} ({', '.join(row['priority_reasons']) if row['priority_reasons'] else 'standard'})",
            "",
            "### Question", "", row["question"], "",
            "### Reference Summary", "", row["reference_answer_summary"], "",
            "### Required Points", "", markdown_list(row["required_points"]), "",
            "### Allowed Variations", "", markdown_list(row["allowed_variations"]), "",
            "### Disallowed Claims", "", markdown_list(row["disallowed_claims"]), "",
            "### Generated Answer", "", row["generated_answer"], "",
            "### Expected Sources", "", markdown_list(row["expected_source_doc_ids"]), "",
            "### Returned Sources", "", markdown_list(row["returned_source_doc_ids"]), "",
            "### Retrieved Evidence", "",
        ])
        for index, item in enumerate(evidence_by_eval.get(eval_id, [])[:3], start=1):
            parts.extend([
                f"#### Evidence {index}: {item['doc_id']} / {item['chunk_id']}", "",
                f"> {evidence_excerpt(item['text'])}", "",
            ])
        parts.extend([
            "### Human Review", "",
            "Correctness: [ ]", "Completeness: [ ]", "Faithfulness: [ ]", "Source Support: [ ]", "",
            "Final Failure Type: [ ]", "", "Notes:", "",
            "### Judge Result", "",
            f"Correctness: {row['judge_correctness']} - {row['judge_correctness_reason']}",
            f"Completeness: {row['judge_completeness']} - missing: {dump(row['judge_missing_required_points'])}",
            f"Faithfulness: {row['judge_faithfulness']} - unsupported: {dump(row['judge_unsupported_claims'])}; contradicted: {dump(row['judge_contradicted_claims'])}",
            f"Source Support: {row['judge_source_support']} - {row['judge_source_support_reason']}",
            f"Failure Type: {row['judge_failure_type']}",
            f"Confidence: {row['judge_confidence']}", "",
        ])
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    load_dotenv_file(PROJECT_ROOT / ".env")
    output_dir = PROJECT_ROOT / "results" / "answer_evaluation"
    rubric_by_id = {row.eval_id: row for row in load_answer_eval_rubric(PROJECT_ROOT / "data" / "answer_evaluation" / "answer_eval_diagnostic.csv")}
    generation_rows = {row["eval_id"]: row for row in read_csv(output_dir / "answer_eval_generation.csv") if row["fallback"].lower() == "false"}
    judge_rows = {row["eval_id"]: row for row in read_csv(output_dir / "answer_eval_judge.csv")}
    claim_rows = read_csv(output_dir / "answer_eval_claims.csv")
    claims_by_eval = {eval_id: [row for row in claim_rows if row["eval_id"] == eval_id] for eval_id in generation_rows}
    store = ChromaVectorStore(Settings.from_env().chroma_persist_dir, FROZEN_CHROMA_COLLECTION)

    rows: list[dict[str, Any]] = []
    evidence_by_eval: dict[str, list[dict[str, str]]] = {}
    for eval_id in sorted(generation_rows):
        generation = generation_rows[eval_id]
        judge = judge_rows[eval_id]
        rubric = rubric_by_id[eval_id]
        reasons = priority_reasons(eval_id, rubric.question_type, judge, claims_by_eval.get(eval_id, []))
        evidence_by_eval[eval_id] = chunk_texts(store, json_list(generation["retrieved_chunk_ids"]))
        rows.append({
            "eval_id": eval_id,
            "source_eval_id": rubric.source_eval_id,
            "question": rubric.question,
            "question_type": rubric.question_type,
            "review_priority": "HIGH" if reasons else "NORMAL",
            "priority_reasons": reasons,
            "reference_answer_summary": rubric.reference_answer_summary,
            "required_points": rubric.required_points,
            "allowed_variations": rubric.allowed_variations,
            "disallowed_claims": rubric.disallowed_claims,
            "generated_answer": generation["answer"],
            "expected_source_doc_ids": rubric.expected_source_doc_ids,
            "returned_source_doc_ids": json_list(generation["source_doc_ids"]),
            "retrieved_doc_ids": json_list(generation["retrieved_doc_ids"]),
            "top_1_distance": generation["top_1_distance"],
            "judge_correctness": judge["correctness_score"],
            "judge_correctness_reason": judge["correctness_reason"],
            "judge_completeness": judge["completeness_score"],
            "judge_missing_required_points": json_list(judge["missing_required_points"]),
            "judge_faithfulness": judge["faithfulness_score"],
            "judge_unsupported_claims": json_list(judge["unsupported_claims"]),
            "judge_contradicted_claims": json_list(judge["contradicted_claims"]),
            "judge_source_support": judge["source_support_score"],
            "judge_source_support_reason": judge["source_support_reason"],
            "judge_failure_type": judge["overall_failure_type"],
            "judge_confidence": judge["judge_confidence"],
            "human_correctness": "",
            "human_completeness": "",
            "human_faithfulness": "",
            "human_source_support": "",
            "human_agrees_with_judge": "",
            "human_final_failure_type": "",
            "human_notes": "",
        })
    write_csv(output_dir / "answer_eval_human_review.csv", rows)
    (output_dir / "human_review_packet.md").write_text(build_packet(rows, evidence_by_eval), encoding="utf-8")
    print(json.dumps({"human_review_rows": len(rows), "high_priority_rows": sum(row["review_priority"] == "HIGH" for row in rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
