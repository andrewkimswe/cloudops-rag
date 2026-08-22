# Phase 13. Held-out Evaluation

## 1. Goal

Phase 13 evaluates the frozen retrieval pipeline on the held-out test set for the first time.

The goal is to check whether development-set choices from Phase 11 and Phase 12 hold up on unseen evaluation questions. No parameters are retuned based on held-out results.

## 2. Frozen Configuration

Frozen Final Configuration:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character

embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5

threshold_signal = Top-1 Chroma L2 distance
threshold = 1.042478
```

The configuration and threshold were not changed after observing held-out results.

## 3. Test Dataset

Dataset:

```text
data/evaluation/evaluation_test.csv
```

Counts:

- Total questions: 10
- In-scope: 8
- Out-of-scope: 2
- Single-document: 5
- Multi-document: 3

Because the test set has only 10 questions, one question changes an overall percentage by 10 percentage points. Subset percentages are even more sample-sensitive.

## 4. Retrieval Metrics

Frozen Final Retrieval on held-out in-scope questions:

| Metric | Result |
|---|---:|
| Hit@1 | 87.50% (7/8) |
| Hit@3 | 100.00% (8/8) |
| Hit@5 | 100.00% (8/8) |
| MRR | 0.9375 |

Single-document results:

| Metric | Result |
|---|---:|
| Hit@1 | 100.00% (5/5) |
| Hit@3 | 100.00% (5/5) |
| Hit@5 | 100.00% (5/5) |
| MRR | 1.0000 |

Multi-document results:

| Metric | Result |
|---|---:|
| Any-Hit@1 | 66.67% (2/3) |
| Any-Hit@3 | 100.00% (3/3) |
| Any-Hit@5 | 100.00% (3/3) |
| All-Hit@1 | 0.00% (0/3) |
| All-Hit@3 | 0.00% (0/3) |
| All-Hit@5 | 0.00% (0/3) |
| MRR | 0.8333 |

The final configuration retrieved at least one expected document for every in-scope test question within Top-5, but it did not retrieve all expected documents for any multi-document test question.

## 5. Baseline vs Final

This comparison is post-freeze validation, not configuration selection.

| Metric | Original Baseline `512/0`, k=3 | Frozen Final `1024/128`, k=5 |
|---|---:|---:|
| Configured cutoff Hit | 100.00% (8/8) | 100.00% (8/8) |
| Hit@1 | 75.00% (6/8) | 87.50% (7/8) |
| MRR | 0.8333 | 0.9375 |
| Multi All-Hit at configured cutoff | 0.00% (0/3) | 0.00% (0/3) |

On the 10-question held-out set, the frozen final configuration retrieved at least one expected document within the configured cutoff for 8/8 in-scope questions. The original baseline also retrieved at least one expected document within its configured cutoff for 8/8 in-scope questions.

The final configuration had better Hit@1 and MRR on this small held-out set, but the sample is too small to claim a general performance improvement.

## 6. Threshold / Fallback Results

Frozen threshold:

```text
Top-1 L2 distance <= 1.042478 -> Accept
Top-1 L2 distance > 1.042478  -> Reject / Fallback
```

Held-out threshold confusion matrix:

| Metric | Result |
|---|---:|
| True Accept | 8 |
| False Reject | 0 |
| True Reject | 2 |
| False Accept | 0 |
| In-scope Acceptance Rate | 100.00% (8/8) |
| Out-of-scope Rejection Rate | 100.00% (2/2) |
| False Reject Rate | 0.00% (0/8) |
| False Accept Rate | 0.00% (0/2) |

No threshold retuning was performed after observing this result.

## 7. Dev vs Test Comparison

Retrieval comparison:

| Metric | Dev | Held-out Test |
|---|---:|---:|
| Hit@1 | 75.00% (27/36) | 87.50% (7/8) |
| Hit@3 | 91.67% (33/36) | 100.00% (8/8) |
| Hit@5 | 91.67% (33/36) | 100.00% (8/8) |
| MRR | 0.8408 | 0.9375 |

Threshold comparison:

| Metric | Dev | Held-out Test |
|---|---:|---:|
| In-scope Acceptance | 100.00% (36/36) | 100.00% (8/8) |
| Out-of-scope Rejection | 100.00% (4/4) | 100.00% (2/2) |

The held-out numbers are directionally consistent with the development result, but the held-out set is much smaller. The test result should be read as a 10-question validation snapshot, not a stable benchmark.

## 8. Per-question Failures

All held-out failures are multi-document All-Hit failures under the frozen final configuration:

| id | Expected Docs | Top-1 Doc | Top-5 Docs | First Expected Ranks | Category |
|---|---|---|---|---|---|
| `eval_043` | `k8s_configmaps`, `k8s_secrets` | `k8s_secrets` | `k8s_secrets`, `k8s_secrets`, `k8s_secrets`, `k8s_secrets`, `k8s_secrets` | `k8s_configmaps:OUT`, `k8s_secrets:1` | multi-document incomplete; duplicate document chunks |
| `eval_045` | `aws_alb_troubleshooting`, `aws_ec2_autoscaling_health_checks` | `aws_ec2_autoscaling_unhealthy_instances` | unhealthy instances, ALB troubleshooting, ALB troubleshooting, ALB monitoring, ALB troubleshooting | `aws_alb_troubleshooting:2`, `aws_ec2_autoscaling_health_checks:10` | multi-document incomplete; duplicate document chunks |
| `eval_046` | `aws_rds_troubleshooting`, `aws_vpc_reachability_analyzer` | `aws_rds_troubleshooting` | RDS, RDS, EKS Auto Mode, RDS, RDS | `aws_rds_troubleshooting:1`, `aws_vpc_reachability_analyzer:OUT` | multi-document incomplete; duplicate document chunks |

All three failures were accepted by the threshold because their Top-1 distances were below `1.042478`.

## 9. Multi-document Results

The same pattern from Phase 10 repeated:

- Multi Any-Hit@5 was high: 100.00% (3/3)
- Multi All-Hit@5 was low: 0.00% (0/3)

This means the retriever found at least one relevant document for each multi-document held-out question, but it failed to retrieve all required documents within Top-5.

## 10. Document Diversity

Frozen final Top-5 document diversity on all 10 test queries:

| Metric | Value |
|---|---:|
| Average unique doc count | 2.10 |
| Average duplicate chunk count | 2.90 |
| Average duplicate ratio | 0.58 |
| Average same-document occupancy | 3.70 |
| Max same-document occupancy | 5 |

The multi-document failures show repeated same-document chunks occupying Top-5:

- `eval_043`: all Top-5 chunks came from `k8s_secrets`
- `eval_046`: four of Top-5 chunks came from `aws_rds_troubleshooting`
- `eval_045`: three of Top-5 chunks came from `aws_alb_troubleshooting`, while `aws_ec2_autoscaling_health_checks` appeared only at rank 10

This supports the same duplicate-chunk / limited document-diversity pattern observed in development experiments.

## 11. Threshold Generalization

Development threshold context:

- Dev max in-scope distance: 1.0350
- Dev min out-of-scope distance: 1.0500
- Selected threshold: 1.042478

Held-out threshold context:

- Test max in-scope distance: 0.8953
- Test min out-of-scope distance: 1.3660
- Selected threshold: 1.042478

The held-out set separated cleanly under the frozen threshold:

- No in-scope questions crossed above the threshold.
- No out-of-scope questions fell below the threshold.

This is encouraging but not statistically strong because the held-out out-of-scope subset has only two questions.

## 12. Repeated Failure Modes

Repeated from development:

- Multi-document incomplete retrieval
- Duplicate same-document chunks
- ConfigMap / Secrets evidence imbalance
- RDS + VPC Reachability second-document miss
- High-confidence retrieval that passes threshold even when evidence is incomplete

`eval_043` repeats the ConfigMap/Secrets pattern: Secrets dominates retrieval while ConfigMaps is missing.

`eval_046` repeats the RDS/VPC pattern: RDS dominates retrieval while Reachability Analyzer is missing.

## 13. New Failure Modes

No clearly new failure mode appeared in this held-out run.

The held-out failures are consistent with the known development failure modes around multi-document completeness and document diversity.

## 14. Limitations

The held-out set has only 10 questions:

- 8 in-scope
- 2 out-of-scope
- 3 multi-document

One question changes the overall held-out result by 10 percentage points. One out-of-scope question changes out-of-scope rejection by 50 percentage points.

Retrieval and threshold were evaluated, but answer quality was not. This phase does not measure answer correctness, faithfulness, citation correctness, hallucination rate, RAGAS, or LLM-as-a-judge scores.

## 15. Final Interpretation

On the 10-question held-out set, the frozen final configuration retrieved at least one expected document for every in-scope question within Top-5 and rejected both out-of-scope questions with the frozen threshold.

However, the most important limitation from development remains: multi-document All-Hit is still poor. The system can often retrieve one relevant source, but it does not reliably retrieve all required evidence documents for multi-document CloudOps troubleshooting questions.

No parameters were retuned after this held-out evaluation.
