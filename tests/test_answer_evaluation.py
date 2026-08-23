import csv
import json
from pathlib import Path

from cloudops_rag.evaluation.answer_evaluation import (
    AnswerEvalRubricRow,
    deterministic_evaluate_row,
    load_answer_eval_rubric,
    parse_json_list,
    source_presence,
    validate_answer_eval_rubric,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUBRIC_PATH = PROJECT_ROOT / "data" / "answer_evaluation" / "answer_eval_diagnostic.csv"
EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_full.csv"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "documents.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_answer_eval_diagnostic_schema_and_size() -> None:
    rows = read_csv(RUBRIC_PATH)
    assert len(rows) == 14
    assert list(rows[0].keys()) == [
        "eval_id",
        "source_eval_id",
        "question",
        "question_type",
        "ground_truth_type",
        "expected_source_doc_ids",
        "reference_answer_summary",
        "required_points",
        "allowed_variations",
        "disallowed_claims",
        "expected_fallback",
        "claim_analysis_candidate",
        "notes",
    ]


def test_answer_eval_expected_source_ids_are_valid() -> None:
    rubric_rows = load_answer_eval_rubric(RUBRIC_PATH)
    evaluation_rows = read_csv(EVALUATION_PATH)
    manifest_doc_ids = {row["doc_id"] for row in read_csv(MANIFEST_PATH)}

    errors = validate_answer_eval_rubric(rubric_rows, evaluation_rows, manifest_doc_ids)

    assert errors == []


def test_answer_eval_expected_fallback_consistency() -> None:
    rubric_rows = load_answer_eval_rubric(RUBRIC_PATH)

    fallback_rows = [row for row in rubric_rows if row.expected_fallback]
    answerable_rows = [row for row in rubric_rows if not row.expected_fallback]

    assert len(fallback_rows) == 3
    assert all(row.ground_truth_type == "out_of_scope" for row in fallback_rows)
    assert all(row.expected_source_doc_ids == [] for row in fallback_rows)
    assert all(row.expected_source_doc_ids for row in answerable_rows)


def test_answer_eval_question_type_mix_and_required_cases() -> None:
    rubric_rows = load_answer_eval_rubric(RUBRIC_PATH)
    source_ids = {row.source_eval_id for row in rubric_rows}
    type_counts: dict[str, int] = {}
    for row in rubric_rows:
        type_counts[row.question_type] = type_counts.get(row.question_type, 0) + 1

    assert type_counts == {
        "single-troubleshooting": 5,
        "discrimination": 3,
        "multi-document": 3,
        "out-of-scope": 3,
    }
    assert {"eval_043", "eval_045", "eval_046"}.issubset(source_ids)


def test_generation_result_serialization_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "generation.csv"
    expected_docs = ["k8s_configmaps", "k8s_secrets"]
    retrieved_docs = ["k8s_configmaps", "k8s_resource_management", "k8s_secrets"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["expected_source_doc_ids", "source_doc_ids", "fallback"])
        writer.writeheader()
        writer.writerow(
            {
                "expected_source_doc_ids": json.dumps(expected_docs),
                "source_doc_ids": json.dumps(retrieved_docs),
                "fallback": "false",
            }
        )

    row = read_csv(output)[0]

    assert parse_json_list(row["expected_source_doc_ids"]) == expected_docs
    assert parse_json_list(row["source_doc_ids"]) == retrieved_docs
    assert row["fallback"] == "false"


def test_source_presence_metric() -> None:
    result = source_presence(["aws_alb_troubleshooting"], ["aws_alb_monitoring", "aws_alb_troubleshooting"])

    assert result["matched_source_doc_ids"] == ["aws_alb_troubleshooting"]
    assert result["source_any_hit"] is True
    assert result["source_all_hit"] is True


def test_multi_doc_source_completeness_metric() -> None:
    partial = source_presence(
        ["aws_alb_troubleshooting", "aws_ec2_autoscaling_health_checks"],
        ["aws_alb_troubleshooting"],
    )
    complete = source_presence(
        ["aws_alb_troubleshooting", "aws_ec2_autoscaling_health_checks"],
        ["aws_ec2_autoscaling_health_checks", "aws_alb_troubleshooting"],
    )

    assert partial["source_any_hit"] is True
    assert partial["source_all_hit"] is False
    assert complete["source_all_hit"] is True


def test_deterministic_fallback_metrics() -> None:
    rubric = AnswerEvalRubricRow(
        eval_id="ans_eval_oos",
        source_eval_id="eval_oos",
        question="What is the billing forecast?",
        question_type="out-of-scope",
        ground_truth_type="out_of_scope",
        expected_source_doc_ids=[],
        reference_answer_summary="",
        required_points=[],
        allowed_variations=[],
        disallowed_claims=[],
        expected_fallback=True,
        claim_analysis_candidate=False,
        notes="",
    )

    correct = deterministic_evaluate_row(rubric, {"fallback": "true", "answer": "insufficient", "source_doc_ids": []})
    unsupported = deterministic_evaluate_row(
        rubric,
        {"fallback": "false", "answer": "Use a reserved instance.", "source_doc_ids": ["aws_rds_troubleshooting"]},
    )

    assert correct["fallback_correct"] is True
    assert correct["failure_category"] == "correct_fallback"
    assert unsupported["fallback_correct"] is False
    assert unsupported["unsupported_generation_on_fallback"] is True
    assert unsupported["failure_category"] == "generated_without_support"


def test_deterministic_multi_doc_partial_failure_category() -> None:
    rubric = AnswerEvalRubricRow(
        eval_id="ans_eval_multi",
        source_eval_id="eval_multi",
        question="How do I separate config from secret data?",
        question_type="multi-document",
        ground_truth_type="multi",
        expected_source_doc_ids=["k8s_configmaps", "k8s_secrets"],
        reference_answer_summary="",
        required_points=[],
        allowed_variations=[],
        disallowed_claims=[],
        expected_fallback=False,
        claim_analysis_candidate=True,
        notes="",
    )

    result = deterministic_evaluate_row(
        rubric,
        {"fallback": False, "answer": "Use ConfigMaps for non-secret config.", "source_doc_ids": ["k8s_configmaps"]},
    )

    assert result["source_any_hit"] is True
    assert result["source_all_hit"] is False
    assert result["multi_source_all_hit"] is False
    assert result["failure_category"] == "partial_multi_document_sources"
