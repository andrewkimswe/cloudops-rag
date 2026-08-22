# Experiment Interpretation

This document explains how to interpret the Phase 7-9 retrieval experiments without overstating the results.

Phase 10 has not started.

## 1. Evaluation Scope

Current corpus:

- 20 official AWS/Kubernetes documents
- Domain-specific CloudOps and troubleshooting documentation

Current evaluation data:

- 50 total questions
- 40 development questions
- 10 held-out test questions
- 36 development in-scope questions
- 4 development out-of-scope questions

Currently evaluated:

- Expected document retrieval
- Document ranking
- Hit Rate@k
- MRR
- Multi-document Any-Hit and All-Hit
- Retrieval latency

Not yet evaluated:

- Generated answer correctness
- Faithfulness or groundedness
- Source attribution quality
- Hallucination rate
- Full end-to-end RAG quality
- Full service latency including LLM generation

## 2. Current Baseline

Baseline retrieval configuration:

- Chunking: `chunk_size=512`, `chunk_overlap=0`
- Chunk unit: character
- Embedding: OpenAI `text-embedding-3-small`
- Chroma
- `top_k=3`

Development in-scope results:

- Hit@1 = 80.56% (29/36)
- Hit@3 = 88.89% (32/36)
- MRR = 0.8651

These are retrieval metrics, not answer quality metrics.

## 3. Chunking Result Interpretation

Phase 8 selected candidate:

- `chunk_size=1024`
- `chunk_overlap=128`
- character-based chunks

Development in-scope comparison:

- Baseline `512/0` Hit@3 = 88.89% (32/36)
- Candidate `1024/128` Hit@3 = 91.67% (33/36)

The percentage difference is +2.78 percentage points, but with only 36 in-scope development questions this is a one-question change.

This should not be interpreted as a statistically generalizable retrieval improvement. It is a comparison result used to choose a candidate for subsequent development-set experiments.

## 4. Coverage vs Ranking Quality

The chunking result should be split into two concepts.

Retrieval Coverage:

- `1024/128` increased Top-3 coverage from 32/36 to 33/36.

Ranking Quality:

- `512/0` Hit@1 = 80.56% (29/36)
- `1024/128` Hit@1 = 75.00% (27/36)
- `512/0` MRR = 0.8651
- `1024/128` MRR = 0.8408

The selected chunking candidate improved Top-3 coverage on the development set by one question, while reducing rank-1 accuracy and MRR. This is a coverage-ranking trade-off, not an across-the-board retrieval improvement.

## 5. Why 1024/128 Was Selected

This project prioritizes Retrieval Coverage for downstream RAG generation: the relevant official document should be present in the context given to the LLM.

Under that priority, `1024/128` was selected because it had the highest Hit@3 among the six tested chunking settings.

Secondary observations:

- Chunk count decreased from 841 to 483.
- Index size and embedding cost may be lower.
- Retrieval latency did not materially worsen in the measured run.

These secondary observations are operational trade-offs. They do not prove that smaller index size causes better retrieval quality.

The selected setting is a subsequent-experiment candidate, not a globally optimal chunking strategy.

## 6. Embedding Trade-Off

Phase 9 compared:

- OpenAI `text-embedding-3-small`
- `sentence-transformers/all-MiniLM-L6-v2`

OpenAI results:

- Hit@3 = 91.67% (33/36)
- MRR = 0.8408
- Mean query embedding latency = 185.60 ms
- Requires API key, internet/API availability, and may incur API cost

MiniLM results:

- Hit@3 = 86.11% (31/36)
- MRR = 0.8314
- Mean query embedding latency = 4.71 ms
- Runs locally
- No API key required
- No per-request external API cost
- Offline execution possible after model download

In this experiment environment, MiniLM showed approximately 39x lower mean query embedding latency than the OpenAI API-based embedding. This value is environment-dependent and should not be interpreted as a general model-level performance ratio.

Retrieval quality is the current priority, so OpenAI `text-embedding-3-small` was selected for subsequent experiments. MiniLM remains a meaningful engineering trade-off when local/offline execution and low query embedding latency matter more.

## 7. Small Sample Limitation

This is a small, domain-specific controlled experiment rather than a large-scale production benchmark.

Limitations:

- Small corpus: 20 documents
- Small evaluation dataset: 50 questions
- Development in-scope set: 36 questions
- Manually constructed evaluation questions
- Provider and question-type subsets are small
- Individual question changes materially affect percentages

Provider and question-type metrics are used for diagnostics and error analysis. They are not used to claim general model or corpus superiority.

## 8. Sequential Tuning Limitation

Experiments use sequential tuning:

1. Chunking selection
2. Embedding selection
3. Future Top-k selection

This is practical for a personal portfolio project, but it is not an exhaustive joint search across chunking, embedding, and retrieval depth.

The selected configuration therefore represents the best candidate among the tested sequential choices, not a guaranteed global optimum.

## 9. Multi-Document Retrieval Weakness

Repeated observation:

- Multi-document Any-Hit@3 is high.
- Multi-document All-Hit@3 is low.

Candidate hypotheses:

- H1: chunks from one relevant document may repeatedly occupy top-k positions.
- H2: the second expected document may be pushed outside Top-k.
- H3: dense similarity retrieval may not represent multiple sub-intents evenly.
- H4: simply increasing Top-k may add more duplicate chunks rather than more distinct expected documents.

These are hypotheses. The current evidence does not prove the root cause.

## 10. Persistent Semantic Confusion

Persistent failure cases:

- `eval_007`
- `eval_027`

Expected document:

- `k8s_configmaps`

Observed repeated retrieval:

- `k8s_secrets`

Chunk size, chunk overlap, and embedding model changes did not resolve this in the tested configurations.

Current conclusion:

In the current corpus, evaluation questions, and tested configurations, there is repeated ConfigMap vs Secret retrieval confusion. This is diagnostic evidence that some errors may require retrieval strategy changes rather than only parameter tuning.

These questions should remain in the evaluation set. The project should not remove hard questions to improve headline metrics.

## 11. What Phase 10 Will Measure

Phase 10 should evaluate Top-k while keeping other variables fixed.

It should measure:

- k = 1, 3, 5
- Hit@k
- MRR
- Multi-document Any-Hit@k
- Multi-document All-Hit@k
- `unique_doc_count`: number of distinct `doc_id` values in Top-k
- `duplicate_chunk_count`: `k - unique_doc_count`
- `duplicate_ratio`: `duplicate_chunk_count / k`
- same-document occupancy within Top-k
- context growth as k increases

Tracked hard cases:

- Service + readiness probe
- ALB + Auto Scaling health check
- RDS + VPC Reachability

The goal is to see whether k increases bring the second expected document into context or only add more chunks from the same document.

## 12. What We Intentionally Do Not Optimize Yet

Do not mix these into Phase 10:

- Maximum Marginal Relevance
- Document-level deduplication
- Per-document chunk cap
- Reranking
- Hybrid search
- BM25 + dense retrieval
- Query expansion
- Query rewriting
- Metadata-aware retrieval
- Token-based chunking
- Semantic chunking

These are Future Work or follow-up experiment candidates. Phase 10 should isolate `retrieval_top_k`.

If Top-k alone does not improve multi-document All-Hit, a later experiment comparing MMR or document-level diversification would be meaningful.

## 13. Retrieval Evaluation vs Answer Evaluation

Current evaluation is retrieval evaluation.

A document being successfully retrieved does not guarantee that the LLM will produce a correct, faithful, or well-cited answer.

Answer-level evaluation is separate and should happen after retrieval configuration is finalized.

Future answer-level metrics may include:

- Answer correctness
- Faithfulness / groundedness
- Source or citation correctness
- Out-of-scope rejection quality

## 14. Held-Out Test Policy

Held-out test data remains untouched until final configuration evaluation.

Policy:

- Do not inspect test results before final configuration selection.
- Do not retune configuration after seeing test results.
- Report percentages and raw counts together.
- Do not hide lower test performance.
- Do not edit or remove test questions because they are difficult.
- Perform per-question failure analysis after the test run.
- Avoid explaining test performance before inspecting actual failures.

## 15. Current Interpretation Summary

What has been shown:

- The pipeline can run end-to-end for retrieval experiments.
- Baseline retrieval is measurable and reproducible.
- Chunking choice changes Top-k coverage and ranking quality differently.
- `1024/128` is a reasonable subsequent-experiment chunking candidate under a Top-3 coverage priority.
- OpenAI `text-embedding-3-small` currently provides better development Hit@3 than MiniLM.
- MiniLM provides a strong local/offline latency and dependency trade-off.
- Multi-document All-Hit and ConfigMap vs Secret confusion are important failure cases.

What has not been shown:

- A globally optimal RAG configuration.
- General benchmark superiority over other RAG systems.
- End-to-end answer quality.
- Hallucination control quality.
- Held-out test performance.
