"""Validation and aggregation helpers for answer-quality judge outputs."""

from __future__ import annotations

import json
from typing import Any

SCORE_FIELDS = (
    "correctness_score",
    "completeness_score",
    "faithfulness_score",
    "source_support_score",
)
REASON_FIELDS = (
    "correctness_reason",
    "source_support_reason",
)
LIST_FIELDS = (
    "missing_required_points",
    "unsupported_claims",
    "contradicted_claims",
)
CONFIDENCE_VALUES = {"low", "medium", "high"}
CLAIM_SUPPORT_VALUES = {"supported", "unsupported", "contradicted", "unclear"}
FAILURE_TYPES = {
    "retrieval_failure",
    "generation_failure",
    "combined_failure",
    "no_material_failure",
}


def parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("judge output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("judge output must be a JSON object")
    return parsed


def validate_score(name: str, value: Any) -> int:
    if not isinstance(value, int) or value not in {0, 1, 2}:
        raise ValueError(f"{name} must be an integer in 0, 1, 2")
    return value


def validate_string_list(name: str, value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, (dict, list)):
            normalized.append(json.dumps(item, ensure_ascii=False))
        else:
            normalized.append(str(item))
    return normalized


def validate_judge_output(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in SCORE_FIELDS:
        normalized[field] = validate_score(field, payload.get(field))
    for field in REASON_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        normalized[field] = value.strip()
    for field in LIST_FIELDS:
        normalized[field] = validate_string_list(field, payload.get(field))
    failure_type = payload.get("overall_failure_type")
    if failure_type not in FAILURE_TYPES:
        raise ValueError("overall_failure_type is invalid")
    normalized["overall_failure_type"] = failure_type
    confidence = payload.get("judge_confidence")
    if isinstance(confidence, str):
        confidence = confidence.strip().lower()
    elif isinstance(confidence, (int, float)):
        confidence = "high" if confidence >= 0.8 else "medium" if confidence >= 0.5 else "low"
    if confidence == "moderate":
        confidence = "medium"
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError("judge_confidence is invalid")
    normalized["judge_confidence"] = confidence
    return normalized


def validate_claim_output(payload: dict[str, Any]) -> list[dict[str, Any]]:
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    normalized: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("each claim must be an object")
        claim_id = claim.get("claim_id")
        claim_text = claim.get("claim_text")
        support_status = claim.get("support_status")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")
        if not isinstance(claim_text, str) or not claim_text.strip():
            raise ValueError("claim_text must be a non-empty string")
        if support_status not in CLAIM_SUPPORT_VALUES:
            raise ValueError("support_status is invalid")
        normalized.append(
            {
                "claim_id": claim_id.strip(),
                "claim_text": claim_text.strip(),
                "support_status": support_status,
                "supporting_doc_ids": validate_string_list("supporting_doc_ids", claim.get("supporting_doc_ids", [])),
                "supporting_chunk_ids": validate_string_list("supporting_chunk_ids", claim.get("supporting_chunk_ids", [])),
                "reason": str(claim.get("reason", "")).strip(),
            }
        )
    return normalized


def aggregate_score_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for field in SCORE_FIELDS:
        values = [int(row[field]) for row in rows]
        summary[field] = {
            "score_2_count": values.count(2),
            "score_1_count": values.count(1),
            "score_0_count": values.count(0),
            "average": round(sum(values) / len(values), 4) if values else None,
        }
    return summary


def needs_human_review(row: dict[str, Any]) -> bool:
    if row.get("judge_confidence") == "low":
        return True
    if any(int(row[field]) < 2 for field in SCORE_FIELDS):
        return True
    if row.get("question_type") == "multi-document":
        return True
    unsupported = row.get("unsupported_claims", [])
    if isinstance(unsupported, str):
        unsupported = json.loads(unsupported)
    return bool(unsupported)
