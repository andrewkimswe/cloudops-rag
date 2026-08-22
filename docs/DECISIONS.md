# Technical Decisions

This document records the main technical decisions for the CloudOps Troubleshooting RAG Assistant project.

The goal of this project is not only to build a working RAG demo, but to build a portfolio project that can be explained in backend/infrastructure interviews. Each decision therefore includes the selected option, alternatives, strengths, trade-offs, and why the choice is appropriate for the current project size.

## 1. Backend: FastAPI

### What Was Selected

FastAPI is selected as the backend framework.

### Why It Was Selected

The final service will expose a RAG pipeline through HTTP APIs, starting with a planned `/query` endpoint. FastAPI provides a clean way to define typed request and response schemas, validation rules, error responses, and service boundaries around the RAG application.

This project is backend/infrastructure oriented, so the API layer should look like a real service rather than a notebook-only prototype. FastAPI makes it straightforward to add health checks, debug/evaluation options, and integration tests later.

### Main Alternatives

- Flask
- Spring Boot

### Advantages

- Good fit for Python-based AI/RAG applications.
- Built-in support for Pydantic validation.
- Automatic OpenAPI documentation is useful for portfolio review and API testing.
- Lightweight enough for a focused service.
- Easier to combine with Python RAG libraries than Java-based frameworks.

### Disadvantages / Trade-Offs

- Adds ASGI concepts and runtime choices such as Uvicorn.
- Less batteries-included than a full enterprise framework.
- Not as familiar as Spring Boot in some traditional backend organizations.
- Requires discipline to keep business logic out of route handlers.

### Why It Is Appropriate for This Project Size

The current project needs one focused backend service around a RAG pipeline, not a large enterprise application. FastAPI gives enough structure for production-like service design while keeping the implementation small and explainable.

Flask would be simpler but would require more manual structure for validation and API contracts. Spring Boot would be strong for enterprise backend engineering, but it would add unnecessary complexity because the RAG ecosystem and evaluation scripts are Python-based.

## 2. RAG Framework: LangChain

### What Was Selected

LangChain is selected as the RAG framework, but it will be used selectively.

The project will not hide the core retrieval and evaluation logic completely inside LangChain chains. Retrieval results, document IDs, scores, rankings, and evaluation outputs must remain directly observable in application code.

### Why It Was Selected

LangChain provides common building blocks for RAG systems, including document handling, text splitting, retriever interfaces, vector store integrations, embedding wrappers, and LLM provider integrations. Using it avoids spending too much time re-implementing standard glue code.

However, this project's core value is retrieval quality evaluation. Therefore, experiment configuration, retrieval metrics, fallback behavior, and result logging should be implemented explicitly rather than treated as a black box.

### Main Alternatives

- LlamaIndex
- Framework 없이 직접 구현

### Advantages

- Broad ecosystem and many integrations.
- Makes it easier to swap embedding models, vector stores, and LLM providers.
- Commonly recognized in RAG application development.
- Reduces boilerplate for standard RAG components.
- Helps keep the first working baseline achievable.

### Disadvantages / Trade-Offs

- Can encourage opaque chains where retrieval behavior is difficult to inspect.
- API changes across versions can create maintenance cost.
- Overusing abstractions can make the project harder to explain in interviews.
- Some framework defaults may not match the evaluation methodology.

### Why It Is Appropriate for This Project Size

This is a personal portfolio project with limited scope, but it still needs realistic RAG components. LangChain is appropriate because it accelerates baseline development while allowing the project to keep evaluation logic explicit.

LlamaIndex is strong for document-centered RAG, but it can abstract away more of the retrieval flow than desired for this project. A fully custom implementation would maximize transparency, but it would slow down progress and shift attention away from the main goal: measuring and improving retrieval quality.

## 3. Vector DB: Chroma

### What Was Selected

Chroma is selected as the initial vector database.

### Why It Was Selected

The project needs a local, reproducible vector store for repeated retrieval experiments. Chroma can persist indexes locally, store metadata with vectors, and integrate with LangChain without requiring a separate database server during early development.

Document metadata is important because evaluation is based on `doc_id`. Chroma's metadata handling makes it easier to inspect retrieved documents and connect retrieval results back to source documents.

### Main Alternatives

- FAISS
- Qdrant

### Advantages

- Easy local setup.
- Persistent local storage.
- Good metadata support for document-level evaluation.
- Convenient integration with LangChain.
- Suitable for repeated personal experiments without extra infrastructure.

### Disadvantages / Trade-Offs

- Not the strongest option for production-scale vector infrastructure.
- Less operationally mature than a dedicated vector database such as Qdrant.
- Local persistence is convenient, but it does not demonstrate distributed operations.
- Performance and scaling characteristics may become limiting for larger corpora.

### Why It Is Appropriate for This Project Size

The initial corpus is expected to be around 20 official documents and later expanded for experiments. The main workload is local indexing, retrieval evaluation, and iteration over chunking/embedding/top-k settings. Chroma fits this workflow because it keeps the development loop simple.

FAISS is fast and lightweight, but metadata and persistence would require more custom code. Qdrant is a better production-scale option and may be worth considering later, especially with Docker or server deployment. For the current personal project, Qdrant would add operational complexity before retrieval quality has been validated.

## 4. Embedding Candidate A: OpenAI `text-embedding-3-small`

### What Was Selected

OpenAI `text-embedding-3-small` is selected as one embedding candidate.

It is not selected as the final embedding model yet. It will be compared against the local Sentence Transformers candidate in Phase 9 using the same evaluation dataset and retrieval metrics.

### Why It Was Selected

This model is a practical API-based embedding baseline. It is expected to provide strong retrieval quality with minimal local compute requirements, making it useful as a quality reference point for the project.

### Main Alternatives

- OpenAI larger embedding models
- Other hosted embedding APIs
- Local embedding models only

### Advantages

- Strong general-purpose retrieval quality.
- No local model download or GPU requirement.
- Simple integration through OpenAI and LangChain tooling.
- Useful baseline for comparing whether a local model is "good enough."

### Disadvantages / Trade-Offs

- Requires an external API.
- Has usage cost.
- Requires secret management through `OPENAI_API_KEY`.
- Network latency and provider availability affect execution.
- Reproducibility depends partly on the external provider.

### Why It Is Appropriate for This Project Size

The project needs one strong API-based candidate to compare against a local model. `text-embedding-3-small` is a reasonable balance of quality, cost, and simplicity. It gives the project an industry-relevant baseline without overcomplicating the first embedding comparison.

## 5. Embedding Candidate B: `sentence-transformers/all-MiniLM-L6-v2`

### What Was Selected

`sentence-transformers/all-MiniLM-L6-v2` is selected as one local embedding candidate.

It is not selected as the final embedding model yet. It will be compared against OpenAI `text-embedding-3-small` in Phase 9 using the same evaluation dataset and retrieval metrics.

### Why It Was Selected

This model is lightweight, widely used, and easy to run locally. It allows the project to evaluate a no-external-API retrieval path, which is useful for cost control, offline development, and reproducibility.

### Main Alternatives

- `BAAI/bge-small-en-v1.5`
- Larger Sentence Transformers models
- API embeddings only

### Advantages

- Runs locally.
- No per-request API cost.
- No external API dependency.
- Low latency after model load for a small corpus.
- Good fit for repeatable local experiments.

### Disadvantages / Trade-Offs

- Retrieval quality may be lower than stronger hosted embedding models.
- Requires local model download and dependency management.
- CPU performance may become a bottleneck for larger datasets.
- Model size is small, so it may miss nuance in complex technical documentation.

### Why It Is Appropriate for This Project Size

The current corpus and evaluation workload are small enough for local embeddings. This candidate makes the project more robust because it can be run without an API key, while still enabling a meaningful comparison across retrieval quality, latency, cost, external dependency, and local execution.

## 6. Evaluation Ground Truth: `doc_id`

### What Was Selected

Retrieval ground truth will be tracked by `doc_id`, not `chunk_id`.

### Why It Was Selected

The project plans to experiment with chunk size and chunk overlap. When those parameters change, chunk boundaries also change. If the evaluation dataset used `chunk_id` as ground truth, labels would become unstable across experiments.

Using `doc_id` keeps the evaluation target stable: the retriever should find the correct official document, even if the exact chunk boundary changes.

### Main Alternatives

- `chunk_id`-level ground truth
- Free-text expected answers
- LLM-as-judge grading

### Advantages

- Stable across chunking experiments.
- Easier to label and maintain.
- Directly aligned with source citation requirements.
- Makes Hit Rate@k and MRR straightforward to compute.

### Disadvantages / Trade-Offs

- Coarser than chunk-level evaluation.
- A retrieved chunk may come from the correct document but still be the wrong section.
- Later analysis may need manual inspection or section-level labels for harder cases.

### Why It Is Appropriate for This Project Size

The first evaluation goal is to compare retrieval settings fairly. `doc_id`-level labels are stable, explainable, and maintainable for a personal project. More granular labels can be added later if the project needs deeper error analysis.

## 7. Retrieval Metrics: Hit Rate@k and MRR

### What Was Selected

The initial retrieval metrics are:

- Hit Rate@k
- MRR

### Why They Were Selected

Hit Rate@k answers whether at least one expected document appears in the top-k retrieved results. This is useful because the RAG generator only has a chance to produce a grounded answer if the retriever includes the right source in the context.

MRR, or Mean Reciprocal Rank, measures how early the first relevant document appears. This matters because a document at rank 1 is more useful than the same document at rank 5, especially when the generation step has limited context capacity.

### Main Alternatives

- Recall@k
- Precision@k
- nDCG
- LLM-as-judge answer scoring

### Advantages

- Hit Rate@k is simple and easy to explain.
- MRR captures ranking quality, not only presence.
- Both can be computed without calling an LLM.
- Both work well with document-level ground truth.
- Together they provide a clear baseline for retrieval experiments.

### Disadvantages / Trade-Offs

- Hit Rate@k does not distinguish rank 1 from rank k.
- MRR focuses on the first relevant document and may not fully capture multi-document questions.
- These metrics evaluate retrieval, not final answer correctness.
- Recall@k may still be needed for multi-document questions.

### Why They Are Appropriate for This Project Size

The project first needs lightweight, reproducible retrieval metrics. Hit Rate@k and MRR are enough to compare chunk size, overlap, embedding model, and top-k settings without adding complex judging infrastructure.

The two metrics complement each other: Hit Rate@k shows whether the expected source was retrieved at all, while MRR shows whether it was ranked high enough to be useful.

### Interpretation Boundary

These metrics evaluate retrieval quality, not full RAG answer quality. A document being retrieved in Top-k does not guarantee that the LLM will produce a correct, faithful, or well-cited answer.

For portfolio reporting, retrieval results should be described with both percentages and raw counts when possible, for example `Retrieval Hit@3 = 91.67% (33/36)`. Avoid phrasing this as end-to-end RAG accuracy.

## 8. Corpus Domain: AWS and Kubernetes Official CloudOps / Troubleshooting Documentation

### What Was Selected

The corpus domain is AWS and Kubernetes official CloudOps and troubleshooting documentation.

### Why It Was Selected

CloudOps troubleshooting is a strong RAG domain because answers should be grounded in trusted operational documentation. The questions are practical, source-dependent, and often require precise references to official behavior, configuration, or troubleshooting steps.

This domain also fits the target role. For backend/infrastructure interviews, the project can demonstrate operational understanding, API/service design, evaluation discipline, and practical AI integration without claiming to research AI models.

### Main Alternatives

- General programming documentation
- Company blog posts and community articles
- Stack Overflow or forum data
- Internal incident runbooks

### Advantages

- Official sources are trusted and citeable.
- AWS and Kubernetes are relevant to backend/infrastructure roles.
- Troubleshooting questions naturally test retrieval quality.
- The domain supports out-of-scope fallback testing.
- The corpus can start small and expand incrementally.

### Disadvantages / Trade-Offs

- Official documentation can be long and noisy after HTML extraction.
- Some troubleshooting answers may span multiple documents.
- Documentation changes over time, so source URLs and content snapshots need tracking.
- Vendor docs may use broad navigation/sidebar content that must be cleaned carefully.

### Why It Is Appropriate for This Project Size

The initial scope of about 20 official documents is small enough for a personal project but rich enough to support meaningful retrieval evaluation. It is also realistic for a portfolio: the project can show source selection, metadata design, evaluation dataset construction, and grounded backend service behavior.

## 9. RAG v1 LLM Baseline: OpenAI `gpt-4o-mini`

### What Was Selected

OpenAI `gpt-4o-mini` is selected as the Phase 5 RAG v1 answer generation baseline.

### Why It Was Selected

Phase 5 needs a practical model that can generate concise answers from retrieved context without making the project expensive to run. The goal is not to compare LLMs yet; it is to verify that retrieval context can be passed into an LLM and returned with source documents.

### Main Alternatives

- Larger OpenAI chat models
- Local LLMs
- No LLM, retrieval-only output

### Advantages

- Low-cost baseline for a personal project.
- Simple integration through the OpenAI SDK.
- Strong enough for grounded troubleshooting answers over short retrieved contexts.
- Keeps the initial RAG v1 implementation focused.

### Disadvantages / Trade-Offs

- Requires `OPENAI_API_KEY`.
- Adds external API latency and provider dependency.
- Does not demonstrate local/offline generation.
- LLM output quality is not the primary metric in the early retrieval-focused phases.

### Why It Is Appropriate for This Project Size

The project needs a minimal, explainable generation step after retrieval. `gpt-4o-mini` is appropriate because it keeps cost and complexity low while still allowing an end-to-end "question -> retrieval -> answer + sources" flow.
