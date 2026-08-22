FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROJECT_ROOT=/app \
    CHROMA_PERSIST_DIR=/app/indexes/chroma \
    RUNTIME_STATUS_PATH=/app/data/runtime/document_status.json

WORKDIR /app

RUN adduser --system --group --home /app appuser

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install .

COPY data/manifests ./data/manifests
COPY scripts ./scripts
COPY docs ./docs

RUN mkdir -p /app/indexes/chroma /app/data/runtime /app/data/raw /app/data/processed \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "cloudops_rag.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
