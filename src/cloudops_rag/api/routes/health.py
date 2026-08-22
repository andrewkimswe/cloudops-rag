"""Health routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloudops_rag.api.dependencies import ApiState, get_api_state
from cloudops_rag.api.schemas.common import ErrorResponse

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    chroma_collection: str
    indexed_chunk_count: int


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Checks application availability and Chroma collection access without calling OpenAI.",
    responses={503: {"model": ErrorResponse}},
)
def health(state: Annotated[ApiState, Depends(get_api_state)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        chroma_collection=state.vector_store.collection_name,
        indexed_chunk_count=state.vector_store.collection.count(),
    )
