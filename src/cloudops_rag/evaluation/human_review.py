"""Helpers for human review preparation and judge-human agreement."""

from __future__ import annotations

from typing import Any

HUMAN_SCORE_FIELDS = (
    "human_correctness",
    "human_completeness",
    "human_faithfulness",
    "human_source_support",
)
JUDGE_TO_HUMAN_FIELDS = {
    "judge_correctness": "human_correctness",
    "judge_completeness": "human_completeness",
    "judge_faithfulness": "human_faithfulness",
    "judge_source_support": "human_source_support",
}
FAILURE_TYPES = {
    "no_material_failure",
    "retrieval_failure",
    "generation_failure",
    "combined_failure",
}


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def validate_human_score(value: str, *, allow_blank: bool = True) -> int | None:
    if is_blank(value):
        if allow_blank:
            return None
        raise ValueError("human score is required")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("human score must be 0, 1, or 2") from exc
    if parsed not in {0, 1, 2}:
        raise ValueError("human score must be 0, 1, or 2")
    return parsed


def validate_human_failure_type(value: str, *, allow_blank: bool = True) -> str | None:
    if is_blank(value):
        if allow_blank:
            return None
        raise ValueError("human failure type is required")
    if value not in FAILURE_TYPES:
        raise ValueError("human failure type is invalid")
    return value


def human_review_complete(rows: list[dict[str, str]]) -> bool:
    for row in rows:
        for field in HUMAN_SCORE_FIELDS:
            if validate_human_score(row.get(field, ""), allow_blank=True) is None:
                return False
        if is_blank(row.get("human_agrees_with_judge", "")):
            return False
        if validate_human_failure_type(row.get("human_final_failure_type", ""), allow_blank=True) is None:
            return False
    return True


def score_agreement(judge_score: int, human_score: int) -> dict[str, bool]:
    return {
        "exact": judge_score == human_score,
        "within_1": abs(judge_score - human_score) <= 1,
    }


def calculate_agreement(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not human_review_complete(rows):
        raise ValueError("Human review incomplete")
    summary: dict[str, Any] = {}
    for judge_field, human_field in JUDGE_TO_HUMAN_FIELDS.items():
        pairs = [(int(row[judge_field]), int(row[human_field])) for row in rows]
        summary[judge_field] = {
            "exact_agreement_count": sum(1 for judge, human in pairs if judge == human),
            "within_1_agreement_count": sum(1 for judge, human in pairs if abs(judge - human) <= 1),
            "total": len(pairs),
        }
    return summary
