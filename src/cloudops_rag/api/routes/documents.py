"""Document ingestion/status routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from cloudops_rag.api.dependencies import ApiState, get_api_state
from cloudops_rag.api.errors import ApiError
from cloudops_rag.api.schemas.common import ErrorResponse
from cloudops_rag.api.schemas.documents import (
    DocumentRegistrationRequest,
    DocumentRegistrationResponse,
    DocumentStatusResponse,
)
from cloudops_rag.ingestion.document_service import DocumentStatusRecord

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentRegistrationResponse,
    summary="Ingest a document URL",
    description="Synchronously fetches, cleans, chunks, embeds, and indexes one HTML document into the runtime Chroma collection.",
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def register_document(
    request: DocumentRegistrationRequest,
    state: Annotated[ApiState, Depends(get_api_state)],
) -> DocumentRegistrationResponse:
    source_url = str(request.source_url)
    result = state.ingestion_service.ingest(
        source_url=source_url,
        title=request.title,
        provider=request.provider,
        category=request.category,
    )
    record = result.record
    if record.status == "failed":
        raise ApiError(400, record.error_code or "ingestion_failed", record.message or "Document ingestion failed.")

    return DocumentRegistrationResponse(
        doc_id=record.doc_id,
        status=record.status,
        message=record.message or "Document ingestion completed.",
        source_url=record.source_url,
        chunk_count=record.chunk_count,
        processed_chars=record.processed_chars,
        duplicate=result.duplicate,
        timings_ms=record.timings_ms,
    )


@router.get(
    "/{doc_id}/status",
    response_model=DocumentStatusResponse,
    summary="Get document status",
    description="Returns current registration/manifest status for a document id.",
    responses={404: {"model": ErrorResponse}},
)
def get_document_status(doc_id: str, state: Annotated[ApiState, Depends(get_api_state)]) -> DocumentStatusResponse:
    record = state.ingestion_service.get_status(doc_id)
    if record is not None:
        return status_response(record)

    manifest_document = state.documents.get(doc_id)
    if manifest_document is None:
        raise ApiError(404, "document_not_found", f"Document '{doc_id}' was not found.")
    return DocumentStatusResponse(
        doc_id=doc_id,
        status=manifest_document["status"],
        title=manifest_document.get("title"),
        source_url=manifest_document.get("source_url"),
        message=manifest_document.get("message"),
        provider=manifest_document.get("provider"),
        category=manifest_document.get("category"),
    )


def status_response(record: DocumentStatusRecord) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        doc_id=record.doc_id,
        status=record.status,
        title=record.title,
        source_url=record.source_url,
        message=record.message,
        provider=record.provider,
        category=record.category,
        created_at=record.created_at,
        updated_at=record.updated_at,
        chunk_count=record.chunk_count,
        processed_chars=record.processed_chars,
        error_code=record.error_code,
        timings_ms=record.timings_ms,
    )
