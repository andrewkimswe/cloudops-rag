import csv
import json
from pathlib import Path

import pytest

from cloudops_rag.evaluation.human_review import (
    calculate_agreement,
    human_review_complete,
    score_agreement,
    validate_human_failure_type,
    validate_human_score,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUMAN_REVIEW_PATH = PROJECT_ROOT / "results" / "answer_evaluation" / "answer_eval_human_review.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_human_review_schema_validation() -> None:
    rows = read_csv(HUMAN_REVIEW_PATH)

    assert len(rows) == 11
    assert list(rows[0].keys()) == [
        "eval_id",
        "source_eval_id",
        "question",
        "question_type",
        "review_priority",
        "priority_reasons",
        "reference_answer_summary",
        "required_points",
        "allowed_variations",
        "disallowed_claims",
        "generated_answer",
        "expected_source_doc_ids",
        "returned_source_doc_ids",
        "retrieved_doc_ids",
        "top_1_distance",
        "judge_correctness",
        "judge_correctness_reason",
        "judge_completeness",
        "judge_missing_required_points",
        "judge_faithfulness",
        "judge_unsupported_claims",
        "judge_contradicted_claims",
        "judge_source_support",
        "judge_source_support_reason",
        "judge_failure_type",
        "judge_confidence",
        "human_correctness",
        "human_completeness",
        "human_faithfulness",
        "human_source_support",
        "human_agrees_with_judge",
        "human_final_failure_type",
        "human_notes",
    ]


def test_blank_human_fields_are_allowed_and_present() -> None:
    rows = read_csv(HUMAN_REVIEW_PATH)
    human_fields = [
        "human_correctness",
        "human_completeness",
        "human_faithfulness",
        "human_source_support",
        "human_agrees_with_judge",
        "human_final_failure_type",
        "human_notes",
    ]

    assert all(row[field] == "" for row in rows for field in human_fields)
    assert human_review_complete(rows) is False


def test_invalid_human_score_rejected() -> None:
    assert validate_human_score("", allow_blank=True) is None
    assert validate_human_score("2") == 2
    with pytest.raises(ValueError, match="0, 1, or 2"):
        validate_human_score("3")
    with pytest.raises(ValueError, match="0, 1, or 2"):
        validate_human_score("yes")


def test_invalid_human_failure_type_rejected() -> None:
    assert validate_human_failure_type("", allow_blank=True) is None
    assert validate_human_failure_type("retrieval_failure") == "retrieval_failure"
    with pytest.raises(ValueError, match="invalid"):
        validate_human_failure_type("semantic_failure")


def test_incomplete_review_detection() -> None:
    rows = [
        {
            "human_correctness": "2",
            "human_completeness": "2",
            "human_faithfulness": "2",
            "human_source_support": "",
            "human_agrees_with_judge": "true",
            "human_final_failure_type": "no_material_failure",
        }
    ]

    assert human_review_complete(rows) is False
    with pytest.raises(ValueError, match="Human review incomplete"):
        calculate_agreement(rows)


def test_agreement_calculation() -> None:
    rows = [
        {
            "judge_correctness": "2",
            "judge_completeness": "1",
            "judge_faithfulness": "2",
            "judge_source_support": "1",
            "human_correctness": "2",
            "human_completeness": "2",
            "human_faithfulness": "1",
            "human_source_support": "0",
            "human_agrees_with_judge": "false",
            "human_final_failure_type": "generation_failure",
        }
    ]

    agreement = calculate_agreement(rows)

    assert score_agreement(2, 2) == {"exact": True, "within_1": True}
    assert agreement["judge_correctness"] == {"exact_agreement_count": 1, "within_1_agreement_count": 1, "total": 1}
    assert agreement["judge_source_support"] == {"exact_agreement_count": 0, "within_1_agreement_count": 1, "total": 1}


def test_review_sheet_json_columns_are_parseable() -> None:
    rows = read_csv(HUMAN_REVIEW_PATH)
    json_fields = [
        "priority_reasons",
        "required_points",
        "allowed_variations",
        "disallowed_claims",
        "expected_source_doc_ids",
        "returned_source_doc_ids",
        "retrieved_doc_ids",
        "judge_missing_required_points",
        "judge_unsupported_claims",
        "judge_contradicted_claims",
    ]

    for row in rows:
        for field in json_fields:
            assert isinstance(json.loads(row[field]), list)


def test_high_priority_cases_are_marked() -> None:
    rows = {row["eval_id"]: row for row in read_csv(HUMAN_REVIEW_PATH)}

    for eval_id in ["ans_eval_007", "ans_eval_009", "ans_eval_010", "ans_eval_011"]:
        assert rows[eval_id]["review_priority"] == "HIGH"
        assert "explicit_high_priority" in json.loads(rows[eval_id]["priority_reasons"])
