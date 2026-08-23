import json

import pytest

from cloudops_rag.evaluation.answer_judge import (
    aggregate_score_distribution,
    needs_human_review,
    parse_json_object,
    validate_claim_output,
    validate_judge_output,
)


def valid_judge_payload() -> dict[str, object]:
    return {
        "correctness_score": 2,
        "correctness_reason": "The core answer matches the rubric.",
        "completeness_score": 1,
        "missing_required_points": ["check endpoints"],
        "faithfulness_score": 2,
        "unsupported_claims": [],
        "contradicted_claims": [],
        "source_support_score": 1,
        "source_support_reason": "Sources support only part of the answer.",
        "overall_failure_type": "generation_failure",
        "judge_confidence": "medium",
    }


def test_judge_schema_validation_accepts_valid_payload() -> None:
    normalized = validate_judge_output(valid_judge_payload())

    assert normalized["correctness_score"] == 2
    assert normalized["missing_required_points"] == ["check endpoints"]
    assert normalized["overall_failure_type"] == "generation_failure"


def test_invalid_judge_output_handling() -> None:
    payload = valid_judge_payload()
    payload["correctness_score"] = 5

    with pytest.raises(ValueError, match="correctness_score"):
        validate_judge_output(payload)

    with pytest.raises(ValueError, match="valid JSON"):
        parse_json_object("not json")


def test_score_range_validation_rejects_string_scores() -> None:
    payload = valid_judge_payload()
    payload["faithfulness_score"] = "2"

    with pytest.raises(ValueError, match="faithfulness_score"):
        validate_judge_output(payload)


def test_claim_support_serialization_and_validation() -> None:
    raw = {
        "claims": [
            {
                "claim_id": "c1",
                "claim_text": "The Service selector should match backend Pod labels.",
                "support_status": "supported",
                "supporting_doc_ids": ["k8s_debug_services"],
                "supporting_chunk_ids": ["k8s_debug_services__chunk_0001"],
                "reason": "The retrieved context discusses selectors and endpoints.",
            }
        ]
    }

    claims = validate_claim_output(json.loads(json.dumps(raw)))

    assert claims[0]["support_status"] == "supported"
    assert claims[0]["supporting_doc_ids"] == ["k8s_debug_services"]


def test_claim_support_validation_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="support_status"):
        validate_claim_output(
            {
                "claims": [
                    {
                        "claim_id": "c1",
                        "claim_text": "A claim",
                        "support_status": "maybe",
                        "supporting_doc_ids": [],
                        "supporting_chunk_ids": [],
                        "reason": "",
                    }
                ]
            }
        )


def test_failure_classification_values_are_validated() -> None:
    payload = valid_judge_payload()
    payload["overall_failure_type"] = "semantic_confusion"

    with pytest.raises(ValueError, match="overall_failure_type"):
        validate_judge_output(payload)


def test_result_aggregation() -> None:
    rows = [
        {
            "correctness_score": 2,
            "completeness_score": 2,
            "faithfulness_score": 2,
            "source_support_score": 2,
        },
        {
            "correctness_score": 1,
            "completeness_score": 0,
            "faithfulness_score": 1,
            "source_support_score": 0,
        },
    ]

    summary = aggregate_score_distribution(rows)

    assert summary["correctness_score"] == {"score_2_count": 1, "score_1_count": 1, "score_0_count": 0, "average": 1.5}
    assert summary["completeness_score"]["score_0_count"] == 1


def test_human_review_flagging() -> None:
    row = {
        "correctness_score": 2,
        "completeness_score": 2,
        "faithfulness_score": 2,
        "source_support_score": 2,
        "judge_confidence": "high",
        "question_type": "single-troubleshooting",
        "unsupported_claims": [],
    }
    assert needs_human_review(row) is False

    row["question_type"] = "multi-document"
    assert needs_human_review(row) is True

    row["question_type"] = "single-troubleshooting"
    row["unsupported_claims"] = ["unsupported claim"]
    assert needs_human_review(row) is True


def test_numeric_judge_confidence_is_normalized() -> None:
    payload = valid_judge_payload()
    payload["judge_confidence"] = 0.9

    normalized = validate_judge_output(payload)

    assert normalized["judge_confidence"] == "high"
