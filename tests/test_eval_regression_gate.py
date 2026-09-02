from __future__ import annotations

from scripts.check_eval_regression import check_gates


def baseline() -> dict:
    return {
        "fail_gates": {
            "dev_hit_at_3": {"minimum_numerator": 33, "denominator": 36},
            "heldout_hit_at_3": {"minimum_numerator": 8, "denominator": 8},
        },
        "warning_gates": {
            "dev_multi_all_hit_at_5": {"reference_numerator": 2, "denominator": 6},
        },
    }


def test_regression_gate_passes_required_metrics_at_baseline() -> None:
    results = check_gates(
        baseline(),
        {
            "dev_hit_at_3": 33,
            "heldout_hit_at_3": 8,
            "dev_multi_all_hit_at_5": 2,
        },
    )

    assert all(result.passed for result in results)


def test_regression_gate_fails_required_metric_below_baseline() -> None:
    results = check_gates(
        baseline(),
        {
            "dev_hit_at_3": 32,
            "heldout_hit_at_3": 8,
            "dev_multi_all_hit_at_5": 2,
        },
    )

    failures = [result for result in results if not result.passed and not result.warning_only]
    assert [failure.name for failure in failures] == ["dev_hit_at_3"]


def test_multi_document_gate_is_warning_only() -> None:
    results = check_gates(
        baseline(),
        {
            "dev_hit_at_3": 33,
            "heldout_hit_at_3": 8,
            "dev_multi_all_hit_at_5": 1,
        },
    )

    warnings = [result for result in results if not result.passed and result.warning_only]
    failures = [result for result in results if not result.passed and not result.warning_only]
    assert [warning.name for warning in warnings] == ["dev_multi_all_hit_at_5"]
    assert failures == []
