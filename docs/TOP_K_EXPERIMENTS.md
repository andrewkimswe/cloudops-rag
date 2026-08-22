# Phase 10. Top-k Experiments

## 1. Experiment Goal

This experiment measures how retrieval quality and context size change when the retrieval cutoff increases from k=1 to k=3 to k=5.

The goal is not to improve the retriever with a new algorithm. The goal is to choose a practical Top-k value for the current RAG v1 configuration before moving to later retrieval quality improvements.

Previous experiment context:

- Phase 7 baseline: `512/0`, OpenAI, k=3, Hit@3 = 88.89% (32/36), MRR = 0.8651.
- Phase 8 candidate: `1024/128`, Hit@3 = 91.67% (33/36), MRR = 0.8408. This improved coverage by one question while lowering ranking quality.
- Phase 9 embedding comparison: with `1024/128` fixed, OpenAI reached Hit@3 = 91.67%, MRR = 0.8408, while MiniLM reached Hit@3 = 86.11%, MRR = 0.8314. OpenAI remains the retrieval-quality candidate, and MiniLM remains the local/offline/low-latency alternative.
- Phase 10 therefore fixes `1024/128` and OpenAI, then changes only Top-k.

## 2. Fixed Configuration

- Corpus: 20 AWS/Kubernetes official CloudOps and troubleshooting documents
- Evaluation dataset: `data/evaluation/evaluation_dev.csv`
- Held-out test set: not used
- Chunking: `chunk_size=1024`, `chunk_overlap=128`, `chunk_unit=character`
- Chunk count: 483
- Embedding model: OpenAI `text-embedding-3-small`
- Vector DB: persistent Chroma
- Chroma collection: `cloudops_rag_v1_embedding_openai_text_embedding_3_small`
- Retrieval algorithm: unchanged vector similarity search
- LLM answer quality: not evaluated

## 3. Evaluation Method

Each dev-set query was retrieved once with `evaluation_depth=10`. The same ranked result list was then cut to k=1, k=3, and k=5.

This keeps the comparison fair because k=1, k=3, and k=5 are evaluated from the same retrieval ranking, not from separate retrieval runs.

k=10 was added only as a diagnostic view because k=5 still had low multi-document All-Hit and some expected documents appeared at rank 6-10.

## 4. k=1 / 3 / 5 Results

| k | Overall Hit | Overall Hit % | MRR | Single Hit | Multi Any-Hit | Multi All-Hit |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 27/36 | 75.00% | 0.8408 | 22/30 | 5/6 | 0/6 |
| 3 | 33/36 | 91.67% | 0.8408 | 27/30 | 6/6 | 0/6 |
| 5 | 33/36 | 91.67% | 0.8408 | 27/30 | 6/6 | 2/6 |
| 10 diagnostic | 35/36 | 97.22% | 0.8408 | 29/30 | 6/6 | 3/6 |

## 5. Raw Count + Percentage

k=1 retrieves at least one expected document for 27 of 36 in-scope questions.

k=3 improves coverage to 33 of 36 in-scope questions, a gain of 6 questions over k=1.

k=5 does not improve overall Hit over k=3, but it improves multi-document All-Hit from 0/6 to 2/6.

k=10 is diagnostic only. It improves overall Hit to 35/36, but the context and duplicate chunk cost are much larger.

## 6. Single-document Analysis

| k | Single Hit | Single Hit % | Single MRR |
|---|---:|---:|---:|
| 1 | 22/30 | 73.33% | 0.8256 |
| 3 | 27/30 | 90.00% | 0.8256 |
| 5 | 27/30 | 90.00% | 0.8256 |
| 10 diagnostic | 29/30 | 96.67% | 0.8256 |

For single-document questions, k=3 captures most of the useful gain. k=5 adds no additional single-document Hit over k=3.

## 7. Multi-document Analysis

| k | Any-Hit | Any-Hit % | All-Hit | All-Hit % |
|---|---:|---:|---:|---:|
| 1 | 5/6 | 83.33% | 0/6 | 0.00% |
| 3 | 6/6 | 100.00% | 0/6 | 0.00% |
| 5 | 6/6 | 100.00% | 2/6 | 33.33% |
| 10 diagnostic | 6/6 | 100.00% | 3/6 | 50.00% |

The main benefit of k=5 is multi-document coverage. k=3 usually retrieves one relevant document, but it often fails to retrieve both expected documents for multi-document questions.

Tracked multi-document cases:

| id | Scenario | Expected Docs | k=3 Result | k=5 Result |
|---|---|---|---|---|
| `eval_021` | Service + readiness probe | `k8s_liveness_readiness_startup_probes`, `k8s_debug_services` | Any-Hit yes, All-Hit no | Any-Hit yes, All-Hit no |
| `eval_023` | ALB + Auto Scaling health check | `aws_alb_troubleshooting`, `aws_ec2_autoscaling_health_checks` | Any-Hit yes, All-Hit no | Any-Hit yes, All-Hit yes |
| `eval_024` | RDS + VPC Reachability | `aws_rds_troubleshooting`, `aws_vpc_reachability_analyzer` | Any-Hit yes, All-Hit no | Any-Hit yes, All-Hit no |

For `eval_021`, `k8s_debug_services` did not appear even within the top 10. For `eval_024`, `aws_vpc_reachability_analyzer` did not appear within the top 10. Increasing Top-k alone does not solve these cases.

## 8. Document Diversity Analysis

| k | Avg Unique Docs | Avg Duplicate Chunks | Avg Duplicate Ratio | Avg Same-doc Occupancy | Max Same-doc Occupancy |
|---|---:|---:|---:|---:|---:|
| 1 | 1.000 | 0.000 | 0.000 | 1.000 | 1 |
| 3 | 1.550 | 1.450 | 0.483 | 2.450 | 3 |
| 5 | 1.975 | 3.025 | 0.605 | 3.775 | 5 |
| 10 diagnostic | 2.600 | 7.400 | 0.740 | 7.375 | 10 |

The results support the duplicate chunk hypothesis as a real retrieval behavior: as k increases, many retrieved chunks come from the same document. This is especially visible in ConfigMap/Secrets and RDS-related cases where one document can occupy most or all of the top results.

This is evidence of low document diversity in the current retrieval setup, but it is not yet a fix. Deduplication, MMR, reranking, or hybrid retrieval are intentionally out of scope for Phase 10.

## 9. Context Growth

| k | Avg Chunks | Avg Characters | Approx Tokens |
|---|---:|---:|---:|
| 1 | 1.0 | 999.5 | 250.0 |
| 3 | 3.0 | 2927.7 | 732.1 |
| 5 | 5.0 | 4941.8 | 1235.6 |
| 10 diagnostic | 10.0 | 9993.0 | 2498.3 |

Approximate token count uses `characters / 4`, so it should be treated as a rough planning estimate.

Moving from k=3 to k=5 adds about 2 retrieved chunks, 2014 characters, and 504 approximate tokens on average. The gain is not overall Hit, but multi-document All-Hit.

## 10. Persistent Failure Cases

| id | Expected Doc | First Expected Rank | k=3 | k=5 | k=10 Diagnostic |
|---|---|---:|---|---|---|
| `eval_002` | `k8s_debug_running_pod` | 7 | miss | miss | hit |
| `eval_007` | `k8s_configmaps` | 8 | miss | miss | hit |
| `eval_019` | `aws_vpc_reachability_analyzer` | 2 | hit | hit | hit |
| `eval_027` | `k8s_configmaps` | OUT | miss | miss | miss |

`eval_002` and `eval_007` are ranking weaknesses: the expected document appears only at rank 7 or 8. `eval_027` is more severe because the expected document does not appear within depth 10.

## 11. ConfigMap / Secrets Confusion

`eval_007` and `eval_027` continue to retrieve `k8s_secrets` ahead of `k8s_configmaps`.

For `eval_007`, `k8s_configmaps` appears at rank 8, so k=10 can surface it diagnostically. For k=3 and k=5, it remains a miss.

For `eval_027`, the top results are dominated by `k8s_secrets`, and `k8s_configmaps` does not appear in the top 10. This suggests a semantic discrimination problem that Top-k tuning alone does not solve.

## 12. Latency Observation

The quality evaluation used one retrieval call per question at `evaluation_depth=10`.

Observed depth-10 retrieval latency:

- Mean: 195.0 ms
- Median: 125.8 ms
- p95: 186.0 ms

A separate k=1/k=3/k=5 latency benchmark was not run in this phase. These latency numbers are environment-dependent because query embedding uses an external OpenAI API call.

## 13. Selected Top-k

Selected Top-k for the next phase: `k=5`.

## 14. Selection Rationale

k=3 and k=5 have the same overall Hit@k: 33/36, or 91.67%.

k=5 is selected because the project includes multi-document troubleshooting scenarios, and k=5 improves multi-document All-Hit from 0/6 to 2/6 while keeping context growth still manageable for RAG v1.

## 15. Trade-offs

Benefits of k=5:

- Preserves k=3 overall Hit@k.
- Improves multi-document All-Hit.
- Gives the generation step more evidence for cross-document operational questions.

Costs of k=5:

- Increases average context from about 732 to 1236 approximate tokens.
- Raises duplicate chunk ratio from 0.483 to 0.605.
- Does not improve single-document Hit over k=3.
- Does not fix cases where the correct document is ranked below k=5 or absent from top 10.

## 16. Limitations

This experiment uses only the development set. The held-out test set was not used.

The dataset is still small, so provider-level and question-type-level breakdowns are diagnostic rather than statistically conclusive.

Retrieval metrics do not evaluate final answer quality. A later phase must test whether added context improves answer correctness without increasing noise.

## 17. What Top-k Tuning Could Not Solve

Top-k tuning could not solve:

- ConfigMap vs Secrets semantic confusion in `eval_027`.
- Missing second document for Service + readiness probe in `eval_021`.
- Missing VPC Reachability document for RDS + network pairing in `eval_024`.
- Duplicate same-document chunks occupying much of the retrieved context.

These issues should be addressed in later phases with methods such as threshold/fallback analysis, document diversity controls, reranking, hybrid retrieval, metadata-aware retrieval, or improved evaluation design. Those methods were intentionally not implemented in Phase 10.
