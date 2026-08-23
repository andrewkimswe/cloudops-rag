"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from cloudops_rag.api.metrics import CONTENT_TYPE_LATEST, render_metrics


router = APIRouter(tags=["monitoring"])


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Exposes process and CloudOps RAG API metrics without calling OpenAI or Chroma.",
)
def metrics() -> Response:
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)
