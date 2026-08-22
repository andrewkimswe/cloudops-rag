"""Document endpoint schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


DocumentStatus = Literal["pending", "processing", "completed", "failed"]


class DocumentRegistrationRequest(BaseModel):
    source_url: HttpUrl = Field(..., examples=["https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/"])
    title: str | None = Field(None, examples=["Debug Pods"])
    provider: str | None = Field(None, examples=["kubernetes"])
    category: str | None = Field(None, examples=["pod_troubleshooting"])


class DocumentRegistrationResponse(BaseModel):
    doc_id: str
    status: DocumentStatus
    message: str
    source_url: str | None = None
    chunk_count: int | None = None
    processed_chars: int | None = None
    duplicate: bool = False
    timings_ms: dict[str, float] | None = None


class DocumentStatusResponse(BaseModel):
    doc_id: str
    status: DocumentStatus
    title: str | None = None
    source_url: str | None = None
    message: str | None = None
    provider: str | None = None
    category: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    chunk_count: int | None = None
    processed_chars: int | None = None
    error_code: str | None = None
    timings_ms: dict[str, float] | None = None
