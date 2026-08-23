# Retrieval Diversification Experiment

## 1. Motivation

Previous retrieval and answer-quality diagnostics showed a repeated failure mode: one document can occupy several Top-k slots with multiple chunks, leaving too little room for a second evidence document in multi-document questions.

This experiment tests one minimal intervention: limit each `doc_id` to at most 2 chunks in the final Top-5 retrieval result.

This is not Phase 18 Monitoring and does not change the production or frozen RAG configuration. It was conducted after the original held-out evaluation, so the existing held-out set was not reused and cap=2 was not promoted to the frozen configuration.

## 2. Observed Failure

Prior observations:

- Development Multi-document All-Hit@5: 2/6
- Held-out Multi-document All-Hit@5: 0/3
- Development Top-5 average unique docs: about 1.975
- Development Top-5 duplicate ratio: about 0.605
- Held-out Top-5 average unique docs: about 2.10
- Held-out Top-5 duplicate ratio: about 0.58

Answer Evaluation diagnostics motivated this experiment by showing that missing second-document evidence was associated with lower answer completeness or correctness in cases such as `eval_043` and `eval_046`. This experiment did not rerun answer generation, so it does not show that cap=2 improved answer quality.

## 3. Hypothesis

Hypothesis:

> Top-k slots are often occupied by repeated chunks from the same document, which can push the second relevant document out of the final context for multi-document CloudOps questions.

## 4. Experimental Change

Baseline:

```text
dense similarity retrieval
raw Chroma ranking
final top_k = 5
no document cap
```

Experimental variant:

```text
dense similarity retrieval unchanged
raw Chroma ranking depth = 20
final top_k = 5
per-document max chunks = 2
```

The cap is applied as a post-processing step that preserves raw similarity order among selected chunks. MMR, BM25, hybrid search, reranking, query rewriting, embedding changes, chunking changes, threshold changes, and prompt changes were not used.

## 5. Controlled Variables

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character
embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
collection = cloudops_rag_v1_embedding_openai_text_embedding_3_small
final_top_k = 5
threshold = 1.042478
LLM generation = not used
LLM judge = not used
```

## 6. Dataset

Dataset: `data/evaluation/evaluation_dev.csv`

Held-out Test was not used. This is a Dev-side exploratory controlled experiment only. Because this experiment is post-hoc relative to the original held-out validation, its results should be treated as candidate evidence, not as a new validated final configuration.

Counts:

| Split | Count |
|---|---:|
| Dev total | 40 |
| In-scope | 36 |
| Single-document | 30 |
| Multi-document | 6 |
| Out-of-scope | 4 |

## 7. Metrics

Retrieval metrics:

- Hit@1, Hit@3, Hit@5
- MRR
- Multi-document Any-Hit@k
- Multi-document All-Hit@k

Document diversity metrics:

- `unique_doc_count`: number of distinct `doc_id` values in final Top-5.
- `duplicate_chunk_count`: `retrieved_chunk_count - unique_doc_count`.
- `duplicate_ratio`: `duplicate_chunk_count / retrieved_chunk_count`.
- `max_same_document_occupancy`: maximum number of Top-5 chunks occupied by one document.

Context metrics:

- average context characters
- approximate tokens, using characters / 4

Latency metrics:

- mean
- median
- p95

Latency is diagnostic only. The cap is Python-level post-processing and should not be over-interpreted relative to query embedding/network latency.

## 8. Baseline

Baseline Dev in-scope retrieval:

| Metric | Result |
|---|---:|
| Hit@1 | 27/36 = 0.7500 |
| Hit@3 | 33/36 = 0.9167 |
| Hit@5 | 33/36 = 0.9167 |
| MRR | 0.8333 |

Single-document baseline:

| Metric | Result |
|---|---:|
| Hit@1 | 22/30 = 0.7333 |
| Hit@3 | 27/30 = 0.9000 |
| Hit@5 | 27/30 = 0.9000 |
| MRR | 0.8167 |

Multi-document baseline:

| Metric | Result |
|---|---:|
| Any-Hit@5 | 6/6 = 1.0000 |
| All-Hit@5 | 2/6 = 0.3333 |
| MRR | 0.9167 |

## 9. Per-document Cap Result

cap=2 Dev in-scope retrieval:

| Metric | Result |
|---|---:|
| Hit@1 | 27/36 = 0.7500 |
| Hit@3 | 34/36 = 0.9444 |
| Hit@5 | 34/36 = 0.9444 |
| MRR | 0.8426 |

Single-document cap=2:

| Metric | Result |
|---|---:|
| Hit@1 | 22/30 = 0.7333 |
| Hit@3 | 28/30 = 0.9333 |
| Hit@5 | 28/30 = 0.9333 |
| MRR | 0.8278 |

Multi-document cap=2:

| Metric | Result |
|---|---:|
| Any-Hit@5 | 6/6 = 1.0000 |
| All-Hit@5 | 4/6 = 0.6667 |
| MRR | 0.9167 |

## 10. Multi-document Analysis

| ID | Expected docs | Baseline Top-5 docs | cap=2 Top-5 docs | Baseline All-Hit@5 | cap=2 All-Hit@5 |
|---|---|---|---|---:|---:|
| eval_020 | k8s_configmaps, k8s_secrets | k8s_secrets repeated + aws_eks_auto_mode_troubleshooting | k8s_secrets, aws_eks_auto_mode_troubleshooting, k8s_debug_running_pod, k8s_horizontal_pod_autoscaling | 0 | 0 |
| eval_021 | k8s_liveness_readiness_startup_probes, k8s_debug_services | probes, hpa, debug_running_pod | probes, hpa, debug_running_pod | 0 | 0 |
| eval_022 | k8s_debug_pods, k8s_resource_management | resource_management repeated | resource_management, debug_pods, debug_running_pod | 0 | 1 |
| eval_023 | aws_alb_troubleshooting, aws_ec2_autoscaling_health_checks | autoscaling_unhealthy_instances, autoscaling_health_checks, alb_troubleshooting | autoscaling_unhealthy_instances, autoscaling_health_checks, alb_troubleshooting | 1 | 1 |
| eval_024 | aws_rds_troubleshooting, aws_vpc_reachability_analyzer | rds_troubleshooting repeated | rds_troubleshooting, vpc_reachability_analyzer | 0 | 1 |
| eval_025 | aws_eks_iam_troubleshooting, aws_eks_auto_mode_troubleshooting | eks_auto_mode, eks_iam | eks_auto_mode, eks_iam | 1 | 1 |

The main change is that cap=2 allowed the second expected document into Top-5 for `eval_022` and `eval_024`. It did not help `eval_020` because `k8s_configmaps` did not appear within raw retrieval depth 20, and it did not help `eval_021` because `k8s_debug_services` was raw rank 14 but still not selected into final Top-5 after the cap. This separates two failure modes: relevant documents that are present but suppressed by duplicate occupancy, and relevant documents that are absent from the raw candidate pool or still too low after capping.

## 11. Single-document Regression

No single-document regression was observed in this Dev run.

Single-document Hit@5 changed from 27/30 to 28/30, and single-document MRR changed from 0.8167 to 0.8278. The improved single-document case was `eval_007`, where ConfigMaps entered Top-5 after repeated Secret chunks were capped.

This does not prove cap=2 is generally safe. It only indicates no regression on the 30 Dev single-document rows in this run.

## 12. Document Diversity

| Metric | Baseline | cap=2 |
|---|---:|---:|
| Average unique doc count | 1.9750 | 2.9500 |
| Average duplicate chunk count | 3.0250 | 1.6500 |
| Average duplicate ratio | 0.6050 | 0.3654 |
| Max same-document occupancy | 5 | 2 |

The cap directly improved document diversity, which supports the duplicate-chunk occupancy part of the hypothesis.

## 13. Hard Cases

| Case | Baseline Top-5 | cap=2 Top-5 | Observation |
|---|---|---|---|
| eval_007 ConfigMap/Secrets | only k8s_secrets | k8s_secrets, k8s_configmaps, k8s_debug_running_pod | Improved; expected ConfigMaps entered Top-5. |
| eval_027 ConfigMap/Secrets | only k8s_secrets | k8s_secrets, k8s_debug_running_pod | Not fixed; expected ConfigMaps absent even within raw depth 20. |
| eval_043 ConfigMap/Secrets | only k8s_secrets | k8s_secrets, k8s_configmaps, other docs | Improved; both expected docs entered Top-5. |
| eval_045 ALB + Auto Scaling | unhealthy_instances, ALB docs, ALB monitoring | unhealthy_instances, ALB docs, ALB monitoring | Exact expected Auto Scaling health-check doc still absent. Alternative support may still be useful for answer quality. |
| eval_046 RDS + VPC | RDS repeated + EKS Auto Mode | RDS, EKS Auto Mode, EKS IAM | Not fixed; VPC Reachability Analyzer absent from Top-5. |

## 14. Trade-offs

What improved:

- Overall Hit@5: 33/36 to 34/36
- Multi-document All-Hit@5: 2/6 to 4/6
- Average unique docs: 1.975 to 2.95
- Duplicate ratio: 0.605 to 0.3654
- Max same-document occupancy: 5 to 2

What did not improve:

- Multi-document Any-Hit@5 was already 6/6.
- `eval_020`, `eval_021`, `eval_027`, and `eval_046` still did not get every needed expected source in final Top-5.
- cap=2 cannot recover a document that is absent from raw depth 20.
- cap=2 can replace highly similar same-document chunks with lower-ranked chunks from other documents, which may introduce less relevant context.

Context size changed modestly:

| Metric | Baseline | cap=2 |
|---|---:|---:|
| Average context characters | 4941.8 | 4461.05 |
| Approximate tokens | 1235.625 | 1115.425 |

Latency impact was negligible for post-processing:

| Metric | cap=2 post-processing |
|---|---:|
| Mean | 0.0276 ms |
| Median | 0.0266 ms |
| p95 | 0.0361 ms |

## 15. Limitations

- Dev-only exploratory experiment; Held-out Test was not reused.
- Small multi-document subgroup: 6 questions.
- Query embedding calls were live OpenAI calls, so latency includes external API/network variability.
- MRR is calculated over the final Top-5 selected result for this controlled experiment.
- No answer generation was run, so answer-quality effects are inferred only from retrieval composition.
- cap=2 is a simple heuristic, not a substitute for MMR, reranking, hybrid retrieval, or query decomposition.

## 16. Decision

cap=2 should be retained as a promising post-hoc candidate, not a production change, and it should not replace the frozen configuration.

The hypothesis is partially supported: document diversity improved substantially, duplicate occupancy decreased, and Multi-document All-Hit@5 improved from 2/6 to 4/6 on the Dev set without observed single-document regression. However, cap=2 did not solve cases where the missing document was not present in raw depth 20 or was still displaced after capping.

Recommendation: retain cap=2 as a promising post-hoc retrieval diversification candidate; do not replace the frozen configuration. If a future scope opens retrieval improvements, compare it against alternatives such as MMR, reranking, hybrid retrieval, or document-aware selection.
