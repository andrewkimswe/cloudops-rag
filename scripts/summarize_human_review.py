#!/usr/bin/env python3
"""Summarize completed human review and judge-human agreement."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.evaluation.human_review import calculate_agreement, human_review_complete, validate_human_failure_type, validate_human_score


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    path = PROJECT_ROOT / "results" / "answer_evaluation" / "answer_eval_human_review.csv"
    rows = read_csv(path)
    reviewed_rows = 0
    for row in rows:
        score_values = [validate_human_score(row.get(field, ""), allow_blank=True) for field in ["human_correctness", "human_completeness", "human_faithfulness", "human_source_support"]]
        validate_human_failure_type(row.get("human_final_failure_type", ""), allow_blank=True)
        if all(value is not None for value in score_values):
            reviewed_rows += 1
    if not human_review_complete(rows):
        print(json.dumps({"status": "Human review incomplete", "reviewed_rows": reviewed_rows, "remaining_rows": len(rows) - reviewed_rows}, ensure_ascii=False))
        return 0
    agreement = calculate_agreement(rows)
    failure_distribution = Counter(row["human_final_failure_type"] for row in rows)
    score_distribution = {
        field: dict(Counter(row[field] for row in rows))
        for field in ["human_correctness", "human_completeness", "human_faithfulness", "human_source_support"]
    }
    print(json.dumps({"status": "Human review complete", "reviewed_rows": len(rows), "agreement": agreement, "human_failure_distribution": dict(failure_distribution), "human_score_distribution": score_distribution}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
