from __future__ import annotations

from types import SimpleNamespace

import pytest
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.generation.openai_llm import OpenAILLM
from cloudops_rag.resilience.retry import RetryPolicy


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class RateLimitError(Exception):
    pass


class BadRequestError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class APIStatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def metric_value(name: str, labels: dict[str, str] | None = None) -> float:
    labels = labels or {}
    text = generate_latest().decode("utf-8")
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name == name and all(sample.labels.get(key) == value for key, value in labels.items()):
                return float(sample.value)
    return 0.0


def test_retry_metric_declares_bounded_labels():
    text = generate_latest().decode("utf-8")

    assert "cloudops_rag_external_retries_total" in text
    assert "operation" in text
    assert "reason" in text


def deterministic_policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, jitter_enabled=False)


def make_embedder(exc: Exception):
    embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
    embedder.model = "text-embedding-3-small"

    class Embeddings:
        def create(self, model, input):
            raise exc

    embedder.client = SimpleNamespace(embeddings=Embeddings())
    return embedder


def make_llm(exc: Exception):
    llm = OpenAILLM.__new__(OpenAILLM)
    llm.model = "gpt-4o-mini"

    class Completions:
        def create(self, model, messages, temperature):
            raise exc

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    return llm


def make_retrying_embedder(failures: list[Exception], delays: list[float]):
    embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
    embedder.model = "text-embedding-3-small"
    embedder.retry_policy = deterministic_policy()
    embedder.retry_sleep = delays.append
    embedder.retry_random = lambda: 0.0
    attempts = {"count": 0}

    class Embeddings:
        def create(self, model, input):
            attempts["count"] += 1
            if failures:
                raise failures.pop(0)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])

    embedder.client = SimpleNamespace(embeddings=Embeddings())
    return embedder, attempts


def make_retrying_llm(failures: list[Exception], delays: list[float]):
    llm = OpenAILLM.__new__(OpenAILLM)
    llm.model = "gpt-4o-mini"
    llm.retry_policy = deterministic_policy()
    llm.retry_sleep = delays.append
    llm.retry_random = lambda: 0.0
    attempts = {"count": 0}

    class Completions:
        def create(self, model, messages, temperature):
            attempts["count"] += 1
            if failures:
                raise failures.pop(0)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="grounded answer"))])

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    return llm, attempts


def test_openai_embedding_timeout_is_normalized():
    with pytest.raises(TimeoutError):
        make_embedder(APITimeoutError()).embed_query("question")


def test_openai_embedding_failure_is_normalized():
    with pytest.raises(RuntimeError):
        make_embedder(APIConnectionError()).embed_query("question")


def test_openai_generation_timeout_is_normalized():
    with pytest.raises(TimeoutError):
        make_llm(APITimeoutError()).answer("question", [])


def test_openai_generation_failure_is_normalized():
    with pytest.raises(RuntimeError):
        make_llm(APIConnectionError()).answer("question", [])


def test_embedding_transient_failure_retries_then_succeeds():
    delays: list[float] = []
    before = metric_value("cloudops_rag_external_retries_total", {"operation": "embedding", "reason": "connection_error"})
    embedder, attempts = make_retrying_embedder([APIConnectionError()], delays)

    assert embedder.embed_query("question") == [0.1, 0.2]

    assert attempts["count"] == 2
    assert delays == [0.25]
    assert metric_value(
        "cloudops_rag_external_retries_total",
        {"operation": "embedding", "reason": "connection_error"},
    ) == before + 1


def test_generation_transient_failures_retry_then_succeed():
    delays: list[float] = []
    before = metric_value("cloudops_rag_external_retries_total", {"operation": "generation", "reason": "server_error"})
    llm, attempts = make_retrying_llm([APIStatusError(503), APIStatusError(502)], delays)

    assert llm.answer("question", []) == "grounded answer"

    assert attempts["count"] == 3
    assert delays == [0.25, 0.5]
    assert metric_value(
        "cloudops_rag_external_retries_total",
        {"operation": "generation", "reason": "server_error"},
    ) == before + 2


def test_embedding_transient_failure_exhaustion_is_normalized():
    delays: list[float] = []
    before = metric_value("cloudops_rag_external_retries_total", {"operation": "embedding", "reason": "rate_limit"})
    embedder, attempts = make_retrying_embedder([RateLimitError(), RateLimitError(), RateLimitError()], delays)

    with pytest.raises(RuntimeError):
        embedder.embed_query("question")

    assert attempts["count"] == 3
    assert delays == [0.25, 0.5]
    assert metric_value(
        "cloudops_rag_external_retries_total",
        {"operation": "embedding", "reason": "rate_limit"},
    ) == before + 2


def test_generation_transient_failure_exhaustion_is_normalized():
    delays: list[float] = []
    before = metric_value("cloudops_rag_external_retries_total", {"operation": "generation", "reason": "connection_error"})
    llm, attempts = make_retrying_llm([APIConnectionError(), APIConnectionError(), APIConnectionError()], delays)

    with pytest.raises(RuntimeError):
        llm.answer("question", [])

    assert attempts["count"] == 3
    assert delays == [0.25, 0.5]
    assert metric_value(
        "cloudops_rag_external_retries_total",
        {"operation": "generation", "reason": "connection_error"},
    ) == before + 2


def test_non_retryable_400_does_not_retry():
    delays: list[float] = []
    before = metric_value("cloudops_rag_external_retries_total", {"operation": "embedding", "reason": "server_error"})
    embedder, attempts = make_retrying_embedder([APIStatusError(400)], delays)

    with pytest.raises(RuntimeError):
        embedder.embed_query("question")

    assert attempts["count"] == 1
    assert delays == []
    assert metric_value(
        "cloudops_rag_external_retries_total",
        {"operation": "embedding", "reason": "server_error"},
    ) == before


def test_authentication_failure_does_not_retry():
    delays: list[float] = []
    embedder, attempts = make_retrying_embedder([AuthenticationError()], delays)

    with pytest.raises(RuntimeError):
        embedder.embed_query("question")

    assert attempts["count"] == 1
    assert delays == []


def test_timeout_does_not_retry():
    delays: list[float] = []
    before = metric_value("cloudops_rag_external_retries_total", {"operation": "generation", "reason": "connection_error"})
    llm, attempts = make_retrying_llm([APITimeoutError()], delays)

    with pytest.raises(TimeoutError):
        llm.answer("question", [])

    assert attempts["count"] == 1
    assert delays == []
    assert metric_value(
        "cloudops_rag_external_retries_total",
        {"operation": "generation", "reason": "connection_error"},
    ) == before
