from __future__ import annotations

from types import SimpleNamespace

import pytest

from cloudops_rag.embedding.openai_embedder import OpenAIEmbedder
from cloudops_rag.generation.openai_llm import OpenAILLM


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


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
