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

## 11. Image Size Audit

Measured on the current Docker build for `cloudops-rag:image-audit`:

| Item | Result |
|---|---:|
| Clean build status | success |
| Clean build duration | 44 seconds |
| `docker images` size | 1.07GB |
| `docker image inspect .Size` | 217,932,432 bytes / 217.93 MB / 207.84 MiB |
| Container root filesystem (`docker inspect -s`) | 848,109,568 bytes |
| Architecture | linux/arm64 |

The `docker images` value is the user-visible Docker CLI image size. The `docker image inspect .Size` value is also recorded because it is the exact field requested for this audit, but it is not the same number users usually see in `docker images`.

Largest Docker history layers:

| Layer | Size |
|---|---:|
| `python -m pip install --upgrade pip && python -m pip install .` | 678MB |
| Debian base layer | 108MB |
| Python runtime build/install layer from `python:3.12.14-slim-bookworm` | 48.4MB |
| base image certificates/netbase/tzdata layer | 10.4MB |
| runtime directory creation and ownership | 1.72MB |
| `COPY src ./src` | 672kB |
| `COPY scripts ./scripts` | 508kB |
| `COPY docs ./docs` | 250kB |

Container filesystem usage:

| Path | Size |
|---|---:|
| `/usr` | 787MB |
| `/usr/local` | 679MB |
| `/usr/local/lib` | 677MB |
| `/usr/local/lib/python3.12/site-packages` | 647MB |
| `/app` | 2MB |

Largest measured site-packages entries:

| Package or directory | Size | Dependency source |
|---|---:|---|
| `kubernetes` | 83MB | transitive dependency of `chromadb` |
| `pandas` | 77MB | direct project dependency |
| `onnxruntime` | 58MB | transitive dependency of `chromadb` |
| `chromadb_rust_bindings` | 52MB | installed with `chromadb` |
| `numpy` | 40MB | direct project dependency; also required by `chromadb`, `pandas`, `onnxruntime`, `langchain-community` |
| `numpy.libs` | 28MB | native libraries installed with `numpy` |
| `langchain_community` | 24MB | direct project dependency |
| `sqlalchemy` | 24MB | transitive dependency of `langchain-community` |
| `zstandard` | 22MB | transitive dependency of `langsmith` / LangChain stack |
| `openai` | 20MB | direct project dependency and required by `langchain-openai` |
| `grpc` | 17MB | transitive dependency of `chromadb` and OpenTelemetry exporter |
| `uvloop` | 16MB | installed through `uvicorn[standard]` |
| `langchain_classic` | 15MB | transitive dependency of `langchain-community` |
| `tokenizers` | 11MB | transitive dependency of `chromadb` |
| `hf_xet` | 11MB | transitive dependency through `huggingface_hub` / `tokenizers` |

Checked optional or suspected large dependencies:

| Package | Docker runtime status |
|---|---|
| `sentence-transformers` | absent |
| `torch` | absent |
| `scipy` | absent |

Project file contribution inside `/app` is small:

| Path | Size |
|---|---:|
| `/app/src` | 644kB |
| `/app/scripts` | 488kB |
| `/app/docs` | 236kB |
| `/app/README.md` | 20kB |
| `/app/pyproject.toml` | 4kB |
| `/app/data/manifests` | 8kB |

Root cause classification:

| Class | Contributor | Evidence |
|---|---|---|
| Primary | Python runtime dependency footprint | pip install layer is 678MB; site-packages is 647MB |
| Secondary | Base Debian/Python runtime layers | Debian base is 108MB; Python runtime layer is 48.4MB |
| Negligible | Application source, docs, scripts, manifests | `/app` totals about 2MB |

The image size is therefore primarily a dependency-packaging issue, not an application-code-size issue. Chroma is a meaningful contributor through its transitive dependencies (`kubernetes`, `onnxruntime`, `chromadb_rust_bindings`, `tokenizers`, `grpcio`, OpenTelemetry packages), but the image is not large because of `sentence-transformers` or `torch`; neither package is installed in the default Docker runtime image.

Future optimization candidates:

| Candidate | Expected impact | Risk | Runtime behavior could change? |
|---|---|---|---|
| Revisit Chroma packaging or vector-store choice | high | medium | yes |
| Split evaluation/analysis dependencies from API runtime dependencies | medium | medium | possibly |
| Reconsider direct runtime need for `pandas` | medium | medium | possibly |
| Avoid `uvicorn[standard]` if standard extras are not required | low to medium | low | possibly |
| Multi-stage build | low | low | unlikely, because there is no large compiler/cache artifact in the final app layer and `PIP_NO_CACHE_DIR=1` is already set |
| Exclude more project files | low | low | no, but `/app` is already only about 2MB |

No optimization was applied in this audit.

## 12. Current Limitations

Docker packaging does not remove the existing project limitations:

- small corpus and evaluation set
- held-out test size is very small
- answer quality is not yet formally evaluated
- multi-document completeness remains weak
- duplicate chunks can still reduce top-k diversity
- semantic confusion cases remain
- runtime corpus expansion can change retrieval score distributions, so the development-selected threshold may require recalibration in production
- Docker image size is still large and is mainly driven by runtime dependency packaging
