"""Common API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["invalid_request"])
    message: str = Field(..., examples=["Request payload is invalid."])


class ErrorResponse(BaseModel):
    error: ErrorDetail
