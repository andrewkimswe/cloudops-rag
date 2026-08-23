# Docker

## 1. Goal

Phase 17 packages the FastAPI + Chroma + OpenAI CloudOps RAG service into a reproducible container runtime.

The Docker setup does not change retrieval settings, threshold tuning, corpus evaluation results, or RAG behavior.

## 2. Build

Build the image:

```bash
docker build -t cloudops-rag:latest .
```

The image uses the project `pyproject.toml` and installs runtime dependencies with:

```bash
pip install .
```

Dev dependencies are not installed in the runtime image.

The optional local embedding dependency is also not installed in the runtime image:

```bash
pip install ".[local]"
```

This keeps `sentence-transformers`, `torch`, and related large local-model dependencies out of the OpenAI-based Docker runtime.

## 3. Run

Run with the local `.env` file mounted as environment variables:

```bash
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  cloudops-rag:latest
```

The container starts uvicorn without development reload:

```text
python -m uvicorn cloudops_rag.api.app:app --host 0.0.0.0 --port 8000
```

## 4. Environment Variables

Required:

- `OPENAI_API_KEY`

Optional runtime paths:

- `PROJECT_ROOT=/app`
- `CHROMA_PERSIST_DIR=/app/indexes/chroma`
- `RUNTIME_STATUS_PATH=/app/data/runtime/document_status.json`

The Docker image does not copy `.env` and does not bake secrets into image layers.

## 5. Volumes

Recommended runtime persistence:

```bash
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/indexes/chroma:/app/indexes/chroma" \
  -v "$(pwd)/data/runtime:/app/data/runtime" \
  cloudops-rag:latest
```

Persistent paths:

- `/app/indexes/chroma`: Chroma collections
- `/app/data/runtime`: runtime document status JSON

Without volumes, runtime-ingested documents and status records are lost when the container is removed. That is normal Docker container behavior.

## 6. Health Check

The Dockerfile includes a Python stdlib health check against:

```text
GET /health
```

The health check verifies the FastAPI process and Chroma collection access. It does not call OpenAI.

## 7. API Smoke Test

Health:

```bash
curl http://localhost:8000/health
```

Metrics:

```bash
curl http://localhost:8000/metrics
```

`/metrics` exposes Prometheus-compatible application metrics and does not call OpenAI or Chroma. The Docker health check remains `/health`.

In-scope query:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Why is my Kubernetes Pod stuck in Pending?"}'
```

Out-of-scope query:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the best laptop to buy for running local LLMs this year?"}'
```

## 8. Runtime Ingestion

Ingest a document:

```bash
curl -X POST http://localhost:8000/documents \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://kubernetes.io/docs/tasks/debug/debug-application/get-shell-running-container/","provider":"kubernetes","category":"runtime_document"}'
```

Check status:

```bash
curl http://localhost:8000/documents/registered_89ae3f83ea6f/status
```

Then query for content that should retrieve the new document.

## 9. Persistence

With volume mounts, runtime state survives container restart:

```text
ingest document -> stop container -> restart with same volumes -> status and Chroma chunks still exist
```

The frozen evaluation collection and mutable runtime collection remain separate:

- Evaluation: `cloudops_rag_v1_embedding_openai_text_embedding_3_small`
- Runtime: `cloudops_rag_runtime_openai_text_embedding_3_small`

Runtime ingestion writes only to the runtime collection.

## 10. Security

Security choices:

- container runs as non-root `appuser`
- `.env` is excluded by `.dockerignore`
- `OPENAI_API_KEY` is injected at runtime
- uvicorn reload is disabled
- Docker health check does not call OpenAI
- local indexes, runtime status, raw processed documents, and results are excluded from the image

## 11. Current Limitations

Docker packaging does not remove the existing project limitations:

- small corpus and evaluation set
- held-out test size is very small
- answer quality is not yet formally evaluated
- multi-document completeness remains weak
- duplicate chunks can still reduce top-k diversity
- semantic confusion cases remain
- runtime corpus expansion can change retrieval score distributions, so the development-selected threshold may require recalibration in production
