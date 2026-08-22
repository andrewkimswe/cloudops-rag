#!/usr/bin/env python3
"""Validate Phase 6 evaluation datasets without running retrieval metrics."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "manifests" / "documents.csv"
FULL_PATH = ROOT / "data" / "evaluation" / "evaluation_full.csv"
DEV_PATH = ROOT / "data" / "evaluation" / "evaluation_dev.csv"
TEST_PATH = ROOT / "data" / "evaluation" / "evaluation_test.csv"

SCHEMA = [
    "id",
    "question",
    "expected_document_1",
    "expected_document_2",
    "ground_truth_type",
    "question_type",
    "expected_answer_summary",
    "usage",
]

QUESTION_TYPES = {
    "single-troubleshooting",
    "single-conceptual",
    "contextual",
    "discrimination",
    "multi-document",
    "out-of-scope",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != SCHEMA:
            raise AssertionError(f"{path}: unexpected schema {reader.fieldnames}")
        return list(reader)


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def load_manifest() -> dict[str, str]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as f:
        return {row["doc_id"]: row["provider"] for row in csv.DictReader(f)}


def expected_docs(row: dict[str, str]) -> list[str]:
    return [
        value
        for value in [row["expected_document_1"].strip(), row["expected_document_2"].strip()]
        if value
    ]


def provider_label(row: dict[str, str], doc_providers: dict[str, str]) -> str:
    docs = [doc for doc in expected_docs(row) if doc != "NONE"]
    if not docs:
        return "out_of_scope"
    providers = {doc_providers[doc] for doc in docs}
    if len(providers) == 1:
        return next(iter(providers))
    return "mixed"


def validate_rows(name: str, rows: list[dict[str, str]], doc_providers: dict[str, str]) -> None:
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"{name}: duplicate IDs found")

    questions = [normalize_question(row["question"]) for row in rows]
    if len(questions) != len(set(questions)):
        raise AssertionError(f"{name}: duplicate questions found")

    for row in rows:
        row_id = row["id"]
        if not row["question"].strip():
            raise AssertionError(f"{name}:{row_id}: empty question")
        if not row["expected_answer_summary"].strip():
            raise AssertionError(f"{name}:{row_id}: empty expected_answer_summary")
        if row["question_type"] not in QUESTION_TYPES:
            raise AssertionError(f"{name}:{row_id}: invalid question_type {row['question_type']}")
        if "expected_chunk" in row:
            raise AssertionError(f"{name}:{row_id}: expected_chunk must not be present")

        docs = expected_docs(row)
        ground_truth_type = row["ground_truth_type"]

        if ground_truth_type == "single":
            if len(docs) != 1 or docs[0] == "NONE":
                raise AssertionError(f"{name}:{row_id}: single rows require one real expected document")
        elif ground_truth_type == "multi":
            if len(docs) != 2 or "NONE" in docs:
                raise AssertionError(f"{name}:{row_id}: multi rows require two real expected documents")
        elif ground_truth_type == "out_of_scope":
            if row["expected_document_1"] != "NONE" or row["expected_document_2"].strip():
                raise AssertionError(f"{name}:{row_id}: out_of_scope rows must use NONE and empty second doc")
        else:
            raise AssertionError(f"{name}:{row_id}: invalid ground_truth_type {ground_truth_type}")

        for doc_id in docs:
            if doc_id != "NONE" and doc_id not in doc_providers:
                raise AssertionError(f"{name}:{row_id}: unknown doc_id {doc_id}")


def summarize(name: str, rows: list[dict[str, str]], doc_providers: dict[str, str]) -> None:
    print(f"{name}: {len(rows)} rows")
    print(f"  question_type: {dict(Counter(row['question_type'] for row in rows))}")
    print(f"  ground_truth_type: {dict(Counter(row['ground_truth_type'] for row in rows))}")
    print(f"  provider: {dict(Counter(provider_label(row, doc_providers) for row in rows))}")


def main() -> int:
    doc_providers = load_manifest()
    full = read_csv(FULL_PATH)
    dev = read_csv(DEV_PATH)
    test = read_csv(TEST_PATH)

    validate_rows("full", full, doc_providers)
    validate_rows("dev", dev, doc_providers)
    validate_rows("test", test, doc_providers)

    full_ids = {row["id"] for row in full}
    dev_ids = {row["id"] for row in dev}
    test_ids = {row["id"] for row in test}
    if dev_ids & test_ids:
        raise AssertionError("Dev/Test ID overlap found")
    if dev_ids | test_ids != full_ids:
        raise AssertionError("Dev/Test IDs do not exactly partition full dataset")

    full_questions = {normalize_question(row["question"]) for row in full}
    dev_questions = {normalize_question(row["question"]) for row in dev}
    test_questions = {normalize_question(row["question"]) for row in test}
    if dev_questions & test_questions:
        raise AssertionError("Dev/Test question overlap found")
    if dev_questions | test_questions != full_questions:
        raise AssertionError("Dev/Test questions do not exactly partition full dataset")

    if not (45 <= len(full) <= 60):
        raise AssertionError("Full evaluation dataset must contain 45-60 questions")
    if not dev or not test:
        raise AssertionError("Dev and test splits must both be non-empty")

    summarize("full", full, doc_providers)
    summarize("dev", dev, doc_providers)
    summarize("test", test, doc_providers)
    print("validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
