import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "diversification_validation.csv"
DEV_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_dev.csv"
TEST_PATH = PROJECT_ROOT / "data" / "evaluation" / "evaluation_test.csv"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "documents.csv"


EXPECTED_FIELDS = [
    "id",
    "question",
    "expected_document_1",
    "expected_document_2",
    "ground_truth_type",
    "question_type",
    "expected_answer_summary",
    "usage",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_diversification_validation_schema_and_size() -> None:
    with VALIDATION_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == EXPECTED_FIELDS
        rows = list(reader)

    assert len(rows) == 12
    assert all(row["usage"] == "diversification_validation" for row in rows)
    assert all(row["question"].strip() for row in rows)
    assert all(row["expected_answer_summary"].strip() for row in rows)
    assert "expected_chunk" not in reader.fieldnames


def test_diversification_validation_is_disjoint_from_existing_eval_ids() -> None:
    validation_ids = {row["id"] for row in read_rows(VALIDATION_PATH)}
    existing_ids = {row["id"] for row in read_rows(DEV_PATH)} | {row["id"] for row in read_rows(TEST_PATH)}

    assert validation_ids
    assert validation_ids.isdisjoint(existing_ids)


def test_diversification_validation_ground_truth_doc_ids_exist() -> None:
    manifest_doc_ids = {row["doc_id"] for row in read_rows(MANIFEST_PATH)}
    rows = read_rows(VALIDATION_PATH)

    for row in rows:
        docs = [doc for doc in [row["expected_document_1"], row["expected_document_2"]] if doc]
        assert all(doc in manifest_doc_ids for doc in docs)
        if row["ground_truth_type"] == "out_of_scope":
            assert docs == []
        elif row["ground_truth_type"] == "single":
            assert len(docs) == 1
        elif row["ground_truth_type"] == "multi":
            assert len(docs) == 2
        else:
            raise AssertionError(f"unexpected ground_truth_type: {row['ground_truth_type']}")
