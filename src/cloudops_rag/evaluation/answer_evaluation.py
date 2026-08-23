"""Deterministic helpers for answer-quality diagnostic evaluation."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnswerEvalRubricRow:
    eval_id: str
    source_eval_id: str
    question: str
    question_type: str
    ground_truth_type: str
    expected_source_doc_ids: list[str]
    reference_answer_summary: str
    required_points: list[str]
    allowed_variations: list[str]
    disallowed_claims: list[str]
    expected_fallback: bool
    claim_analysis_candidate: bool
    notes: str


def parse_json_list(value: str) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("expected a JSON array of strings")
    return parsed


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"expected true/false, got {value!r}")


def load_answer_eval_rubric(path: Path) -> list[AnswerEvalRubricRow]:
    rows: list[AnswerEvalRubricRow] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                AnswerEvalRubricRow(
                    eval_id=raw["eval_id"],
                    source_eval_id=raw["source_eval_id"],
                    question=raw["question"],
                    question_type=raw["question_type"],
                    ground_truth_type=raw["ground_truth_type"],
                    expected_source_doc_ids=parse_json_list(raw["expected_source_doc_ids"]),
                    reference_answer_summary=raw["reference_answer_summary"],
                    required_points=parse_json_list(raw["required_points"]),
                    allowed_variations=parse_json_list(raw["allowed_variations"]),
                    disallowed_claims=parse_json_list(raw["disallowed_claims"]),
                    expected_fallback=parse_bool(raw["expected_fallback"]),
                    claim_analysis_candidate=parse_bool(raw["claim_analysis_candidate"]),
                    notes=raw.get("notes", ""),
                )
            )
    return rows


def validate_answer_eval_rubric(
    rubric_rows: list[AnswerEvalRubricRow],
    evaluation_rows: list[dict[str, str]],
    manifest_doc_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    eval_by_id = {row["id"]: row for row in evaluation_rows}
    seen: set[str] = set()
    for row in rubric_rows:
        if row.eval_id in seen:
            errors.append(f"duplicate eval_id: {row.eval_id}")
        seen.add(row.eval_id)
        source = eval_by_id.get(row.source_eval_id)
        if source is None:
            errors.append(f"{row.eval_id}: unknown source_eval_id {row.source_eval_id}")
            continue
        if source["question"] != row.question:
            errors.append(f"{row.eval_id}: question does not match source evaluation row")
        if source["question_type"] != row.question_type:
            errors.append(f"{row.eval_id}: question_type does not match source evaluation row")
        if source["ground_truth_type"] != row.ground_truth_type:
            errors.append(f"{row.eval_id}: ground_truth_type does not match source evaluation row")
        invalid_docs = [doc_id for doc_id in row.expected_source_doc_ids if doc_id not in manifest_doc_ids]
        if invalid_docs:
            errors.append(f"{row.eval_id}: invalid expected source doc ids {invalid_docs}")
        if row.expected_fallback and row.expected_source_doc_ids:
            errors.append(f"{row.eval_id}: fallback rows must not expect source docs")
        if not row.expected_fallback and not row.expected_source_doc_ids:
            errors.append(f"{row.eval_id}: answerable rows must have expected source docs")
        if row.expected_fallback and row.ground_truth_type != "out_of_scope":
            errors.append(f"{row.eval_id}: expected fallback should use out_of_scope rows")
    return errors


def source_presence(expected_doc_ids: list[str], source_doc_ids: list[str]) -> dict[str, Any]:
    expected = set(expected_doc_ids)
    returned = set(source_doc_ids)
    matched = [doc_id for doc_id in expected_doc_ids if doc_id in returned]
    return {
        "matched_source_doc_ids": matched,
        "source_hit_count": len(matched),
        "source_expected_count": len(expected_doc_ids),
        "source_any_hit": bool(expected and returned.intersection(expected)),
        "source_all_hit": expected.issubset(returned) if expected else False,
    }


def deterministic_evaluate_row(rubric: AnswerEvalRubricRow, generation: dict[str, Any]) -> dict[str, Any]:
    fallback = parse_bool(generation["fallback"])
    answer = str(generation.get("answer", ""))
    source_doc_ids = list(generation.get("source_doc_ids", []))
    presence = source_presence(rubric.expected_source_doc_ids, source_doc_ids)
    empty_answer = (not rubric.expected_fallback) and not answer.strip()
    unsupported_generation_on_fallback = rubric.expected_fallback and (not fallback) and bool(answer.strip())
    if rubric.expected_fallback and fallback:
        failure_category = "correct_fallback"
    elif rubric.expected_fallback and not fallback:
        failure_category = "generated_without_support"
    elif fallback and not rubric.expected_fallback:
        failure_category = "false_fallback"
    elif rubric.ground_truth_type == "multi" and not presence["source_all_hit"]:
        failure_category = "partial_multi_document_sources"
    elif not presence["source_any_hit"]:
        failure_category = "missing_expected_source"
    else:
        failure_category = "answer_generated"
    return {
        "eval_id": rubric.eval_id,
        "source_eval_id": rubric.source_eval_id,
        "expected_fallback": rubric.expected_fallback,
        "actual_fallback": fallback,
        "fallback_correct": rubric.expected_fallback == fallback,
        "empty_missing_answer": empty_answer,
        "unsupported_generation_on_fallback": unsupported_generation_on_fallback,
        "multi_source_all_hit": presence["source_all_hit"] if rubric.ground_truth_type == "multi" else "",
        "failure_category": failure_category,
        **presence,
    }
