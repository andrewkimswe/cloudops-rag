"""Query routes."""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends

from cloudops_rag.api.dependencies import ApiState, get_api_state
from cloudops_rag.api.errors import ApiError
from cloudops_rag.api.schemas.common import ErrorResponse
from cloudops_rag.api.schemas.query import QueryDebug, QueryRequest, QueryResponse, RetrievedChunkDebug, SourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a CloudOps troubleshooting question",
    description="Runs the frozen RAG pipeline with threshold fallback. Reject decisions skip LLM generation.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
def query(request: QueryRequest, state: Annotated[ApiState, Depends(get_api_state)]) -> QueryResponse:
    started = time.perf_counter()
    logger.info("query_start")
    try:
        result = state.rag_service.query(request.question)
    except TimeoutError as exc:
        logger.exception("query_timeout")
        raise ApiError(504, "external_dependency_timeout", "Timed out while calling an external dependency.") from exc
    except RuntimeError as exc:
        logger.exception("query_dependency_failure")
        raise ApiError(503, "external_dependency_unavailable", "A retrieval or generation dependency is unavailable.") from exc
    except Exception as exc:
        logger.exception("query_internal_failure")
        raise ApiError(500, "internal_error", "Query processing failed.") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("query_complete fallback=%s elapsed_ms=%.2f", result.fallback, elapsed_ms)
    debug = None
    if request.debug:
        debug = QueryDebug(
            top_1_distance=result.retrieval_distance,
            distance_threshold=result.distance_threshold,
            retrieval_top_k=state.rag_service.top_k,
            retrieved_chunks=[
                RetrievedChunkDebug(
                    rank=chunk.rank,
                    doc_id=chunk.doc_id,
                    title=chunk.title,
                    chunk_id=chunk.chunk_id,
                    distance=chunk.score,
                )
                for chunk in result.retrieved_chunks
            ],
        )

    return QueryResponse(
        question=result.question,
        answer=result.answer,
        fallback=result.fallback,
        sources=[
            SourceResponse(
                doc_id=source.doc_id,
                title=source.title,
                source_url=source.source_url,
                rank=source.rank,
            )
            for source in result.sources
        ],
        debug=debug,
    )
