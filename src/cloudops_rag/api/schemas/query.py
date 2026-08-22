"""Query endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["Why is my Kubernetes Pod stuck in Pending?"])
    debug: bool = Field(False, description="Include retrieval diagnostics for development/debugging.")

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped


class SourceResponse(BaseModel):
    doc_id: str
    title: str
    source_url: str
    rank: int


class RetrievedChunkDebug(BaseModel):
    rank: int
    doc_id: str
    title: str
    chunk_id: str
    distance: float | None


class QueryDebug(BaseModel):
    top_1_distance: float | None
    distance_threshold: float | None
    retrieval_top_k: int
    retrieved_chunks: list[RetrievedChunkDebug]


class QueryResponse(BaseModel):
    question: str
    answer: str
    fallback: bool
    sources: list[SourceResponse]
    debug: QueryDebug | None = None
