"""FastAPI application for the CloudOps RAG assistant."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from cloudops_rag.api.dependencies import build_api_state
from cloudops_rag.api.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL
from cloudops_rag.api.routes import documents, health, metrics, query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    logger.info("api_startup")
    app.state.api_state = build_api_state()
    yield
    logger.info("api_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CloudOps Troubleshooting RAG Assistant",
        version="0.1.0",
        description="REST API for the frozen CloudOps troubleshooting RAG pipeline.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(documents.router)
    app.include_router(metrics.router)
    register_metrics_middleware(app)
    register_exception_handlers(app)
    return app


def register_metrics_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def prometheus_http_metrics(request: Request, call_next):
        started = time.perf_counter()
        status_code = "500"
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        finally:
            endpoint = route_template(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(time.perf_counter() - started)


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return "unmatched"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail: Any = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            return JSONResponse(status_code=exc.status_code, content={"error": detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "Request validation failed."}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_api_error")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error."}},
        )


app = create_app()
