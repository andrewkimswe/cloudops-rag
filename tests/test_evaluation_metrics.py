from cloudops_rag.evaluation.metrics import (
    hit_at_k,
    multi_all_hit_at_k,
    multi_any_hit_at_k,
    reciprocal_rank,
)


def test_hit_at_k():
    assert hit_at_k({"doc-a"}, ["doc-x", "doc-a", "doc-y"], 3)
    assert not hit_at_k({"doc-a"}, ["doc-x", "doc-y", "doc-z"], 3)
    assert not hit_at_k({"doc-a"}, ["doc-x", "doc-a"], 1)


def test_reciprocal_rank():
    assert reciprocal_rank({"doc-a"}, ["doc-a", "doc-b"]) == 1.0
    assert reciprocal_rank({"doc-a"}, ["doc-b", "doc-a"]) == 0.5
    assert reciprocal_rank({"doc-a"}, ["doc-b", "doc-c"]) == 0.0


def test_multi_document_any_hit_and_all_hit():
    expected = {"doc-a", "doc-b"}
    assert multi_any_hit_at_k(expected, ["doc-x", "doc-a", "doc-y"], 3)
    assert not multi_all_hit_at_k(expected, ["doc-x", "doc-a", "doc-y"], 3)
    assert multi_all_hit_at_k(expected, ["doc-a", "doc-x", "doc-b"], 3)


def test_out_of_scope_is_not_scored_by_accuracy_helpers():
    expected = set()
    assert not hit_at_k(expected, ["doc-a"], 3)
    assert reciprocal_rank(expected, ["doc-a"]) == 0.0

