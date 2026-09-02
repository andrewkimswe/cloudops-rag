#!/usr/bin/env python3
"""Check frozen retrieval/threshold artifacts against regression gates."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "results" / "eval_regression_baseline.json"
TOP_K_SUMMARY_PATH = PROJECT_ROOT / "results" / "top_k" / "top_k_summary.json"
HELDOUT_SUMMARY_PATH = PROJECT_ROOT / "results" / "heldout" / "heldout_summary.json"
THRESHOLD_SUMMARY_PATH = PROJECT_ROOT / "results" / "threshold" / "threshold_summary.json"


@dataclass(frozen=True)
class GateResult:
    name: str
    observed: int
    required: int
    denominator: int
    passed: bool
    warning_only: bool = False


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_top_k_summary(top_k_summary: dict[str, Any], cutoff_k: int) -> dict[str, Any]:
    for row in top_k_summary["summary"]:
        if int(row["cutoff_k"]) == cutoff_k:
            return row
    raise AssertionError(f"top_k_summary.json does not contain cutoff_k={cutoff_k}")


def collect_metrics() -> dict[str, int]:
    top_k_summary = load_json(TOP_K_SUMMARY_PATH)
    heldout_summary = load_json(HELDOUT_SUMMARY_PATH)
    threshold_summary = load_json(THRESHOLD_SUMMARY_PATH)

    top_k_3 = selected_top_k_summary(top_k_summary, cutoff_k=3)
    top_k_5 = selected_top_k_summary(top_k_summary, cutoff_k=5)
    final_heldout = heldout_summary["frozen_final_summary"]
    dev_threshold = threshold_summary["selected_confusion_matrix"]

    return {
        "dev_hit_at_3": int(top_k_3["overall_hit_count"]),
        "heldout_hit_at_3": int(final_heldout["hit_at_3_count"]),
        "dev_oos_reject": int(dev_threshold["true_reject"]),
        "heldout_oos_reject": int(final_heldout["true_reject"]),
        "dev_multi_all_hit_at_5": int(top_k_5["multi_all_hit_count"]),
        "heldout_multi_all_hit_at_5": int(final_heldout["multi_all_hit_at_5_count"]),
    }


def check_gates(baseline: dict[str, Any], observed: dict[str, int]) -> list[GateResult]:
    results: list[GateResult] = []
    for name, gate in baseline["fail_gates"].items():
        value = observed[name]
        required = int(gate["minimum_numerator"])
        results.append(
            GateResult(
                name=name,
                observed=value,
                required=required,
                denominator=int(gate["denominator"]),
                passed=value >= required,
            )
        )

    for name, gate in baseline["warning_gates"].items():
        value = observed[name]
        reference = int(gate["reference_numerator"])
        results.append(
            GateResult(
                name=name,
                observed=value,
                required=reference,
                denominator=int(gate["denominator"]),
                passed=value >= reference,
                warning_only=True,
            )
        )
    return results


def print_results(results: list[GateResult]) -> None:
    for result in results:
        status = "PASS" if result.passed else "WARN" if result.warning_only else "FAIL"
        gate_type = "warning" if result.warning_only else "required"
        print(
            f"{status}: {result.name} observed={result.observed}/{result.denominator} "
            f"{gate_type}>={result.required}/{result.denominator}"
        )


def main() -> int:
    baseline = load_json(BASELINE_PATH)
    observed = collect_metrics()
    results = check_gates(baseline, observed)
    print_results(results)

    failures = [result for result in results if not result.passed and not result.warning_only]
    if failures:
        print("retrieval regression gate: FAIL", file=sys.stderr)
        return 1
    print("retrieval regression gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
