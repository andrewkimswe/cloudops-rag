#!/usr/bin/env python3
"""Summarize completed human review and judge-human agreement."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.evaluation.human_review import calculate_agreement, human_review_complete, validate_human_failure_type, validate_human_score

HUMAN_SCORE_FIELDS = ["human_correctness", "human_completeness", "human_faithfulness", "human_source_support"]
JUDGE_FIELDS = ["judge_correctness", "judge_completeness", "judge_faithfulness", "judge_source_support"]
METRIC_NAMES = ["correctness", "completeness", "faithfulness", "source_support"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def score_distribution(rows: list[dict[str, str]], field: str) -> dict[str, Any]:
    values = [int(row[field]) for row in rows]
    return {
        "score_2_count": values.count(2),
        "score_1_count": values.count(1),
        "score_0_count": values.count(0),
        "mean": round(sum(values) / len(values), 4) if values else None,
    }


def disagreement_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        metric_differences = []
        for metric, judge_field, human_field in zip(METRIC_NAMES, JUDGE_FIELDS, HUMAN_SCORE_FIELDS):
            judge = int(row[judge_field])
            human = int(row[human_field])
            if judge != human:
                metric_differences.append(f"{metric}: judge {judge} -> human {human}")
        if metric_differences or row.get("human_agrees_with_judge") == "false":
            output.append(
                {
                    "eval_id": row["eval_id"],
                    "source_eval_id": row["source_eval_id"],
                    "question_type": row["question_type"],
                    "metric_differences": "; ".join(metric_differences),
                    "judge_failure_type": row["judge_failure_type"],
                    "human_final_failure_type": row["human_final_failure_type"],
                    "human_notes": row["human_notes"],
                }
            )
    return output


def main() -> int:
    output_dir = PROJECT_ROOT / "results" / "answer_evaluation"
    path = output_dir / "answer_eval_human_review.csv"
    rows = read_csv(path)
    reviewed_rows = 0
    for row in rows:
        score_values = [validate_human_score(row.get(field, ""), allow_blank=True) for field in HUMAN_SCORE_FIELDS]
        validate_human_failure_type(row.get("human_final_failure_type", ""), allow_blank=True)
        if all(value is not None for value in score_values):
            reviewed_rows += 1
    if not human_review_complete(rows):
        summary = {"status": "Human review incomplete", "reviewed_rows": reviewed_rows, "remaining_rows": len(rows) - reviewed_rows}
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    agreement = calculate_agreement(rows)
    metric_summary = {metric: score_distribution(rows, field) for metric, field in zip(METRIC_NAMES, HUMAN_SCORE_FIELDS)}
    exact_metric_matches = 0
    within_1_metric_matches = 0
    total_metric_pairs = len(rows) * len(METRIC_NAMES)
    for row in rows:
        for judge_field, human_field in zip(JUDGE_FIELDS, HUMAN_SCORE_FIELDS):
            judge = int(row[judge_field])
            human = int(row[human_field])
            exact_metric_matches += int(judge == human)
            within_1_metric_matches += int(abs(judge - human) <= 1)
    failure_distribution = Counter(row["human_final_failure_type"] for row in rows)
    disagreements = disagreement_rows(rows)
    summary = {
        "status": "Human review complete",
        "reviewed_rows": len(rows),
        "remaining_rows": 0,
        "human_score_distribution": metric_summary,
        "judge_human_agreement": agreement,
        "overall_exact_agreement": {
            "exact_metric_matches": exact_metric_matches,
            "total_metric_pairs": total_metric_pairs,
            "rate": round(exact_metric_matches / total_metric_pairs, 4),
        },
        "overall_within_1_agreement": {
            "within_1_metric_matches": within_1_metric_matches,
            "total_metric_pairs": total_metric_pairs,
            "rate": round(within_1_metric_matches / total_metric_pairs, 4),
        },
        "human_failure_distribution": dict(failure_distribution),
        "disagreement_count": len(disagreements),
    }
    (output_dir / "answer_eval_human_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(
        output_dir / "answer_eval_judge_human_disagreements.csv",
        ["eval_id", "source_eval_id", "question_type", "metric_differences", "judge_failure_type", "human_final_failure_type", "human_notes"],
        disagreements,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
