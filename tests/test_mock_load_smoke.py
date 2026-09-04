from scripts.mock_load_smoke import run_smoke


def test_mock_load_smoke_exercises_success_fallback_and_timeout_paths() -> None:
    summary = run_smoke(requests=20, concurrency=5, latency_ms=0)

    assert summary["requests"] == 20
    assert summary["mock_service_calls"] == 20
    assert summary["status_counts"]["200"] == 18
    assert summary["status_counts"]["504"] == 2
    assert summary["fallback_count"] == 2
    assert summary["error_counts"] == {"external_dependency_timeout": 2}
    assert summary["openai_calls"] == 0
    assert summary["chroma_calls"] == 0
