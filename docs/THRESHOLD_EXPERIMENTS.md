# Phase 12. Similarity Threshold / Fallback Experiment

## 1. Goal

Phase 12 adds a retrieval-confidence gate before LLM generation.

The goal is:

```text
Query
-> retrieve top-5
-> inspect rank-1 retrieval distance
-> accept when confidence is sufficient
-> skip LLM and return fallback when confidence is insufficient
```

This phase evaluates whether a simple retrieval distance threshold can separate in-scope questions from out-of-scope questions on the development set.

## 2. Frozen Retrieval Configuration

The Phase 11 Final Retrieval Configuration is fixed:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character

embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5
collection = cloudops_rag_v1_embedding_openai_text_embedding_3_small
```

No chunking, embedding, vector DB, or Top-k changes were made in Phase 12.

## 3. Threshold Signal

Threshold signal:

```text
Top-1 retrieved chunk L2 distance
```

Decision rule:

```text
top_1_l2_distance <= threshold -> Accept, allow LLM call
top_1_l2_distance > threshold  -> Reject, skip LLM call, return fallback
```

This phase intentionally does not use Top-k average score, weighted score, score gap, a custom confidence model, or an LLM-based relevance judge.

## 4. Chroma Score Semantics

The current retrieval code requests Chroma `distances` and stores the returned value in `RetrievedChunk.score`.

For this project, the current Chroma collection has no explicit `hnsw:space` metadata. In installed Chroma `1.5.9`, the local HNSW parameter implementation defaults `hnsw:space` to `l2` when metadata does not set another value.

Therefore, the current score is:

```text
distance, not similarity
metric = L2
smaller = more similar
larger = less similar
```

The Phase 12 implementation uses variable names and documentation that refer to `distance`, not generic confidence score.

## 5. Dataset

Dataset used:

```text
data/evaluation/evaluation_dev.csv
```

Counts:

- Total dev questions: 40
- In-scope: 36
- Out-of-scope: 4

The held-out test set was not read, scored, or used for threshold selection.

The out-of-scope subset is very small. One out-of-scope question changes the rejection rate by 25 percentage points, so all out-of-scope threshold results are highly sample-sensitive.

## 6. In-scope Score Distribution

Top-1 L2 distance for 36 in-scope questions:

| Metric | Value |
|---|---:|
| count | 36 |
| min | 0.5080 |
| max | 1.0350 |
| mean | 0.7792 |
| median | 0.7893 |
| p10 | 0.6197 |
| p25 | 0.6913 |
| p75 | 0.8592 |
| p90 | 0.9016 |

## 7. Out-of-scope Score Distribution

Top-1 L2 distance for 4 out-of-scope questions:

| Metric | Value |
|---|---:|
| count | 4 |
| min | 1.0500 |
| max | 1.5080 |
| mean | 1.2714 |
| median | 1.2639 |
| p10 | 1.0795 |
| p25 | 1.1238 |
| p75 | 1.4115 |
| p90 | 1.4694 |

## 8. Distribution Overlap

In this development set, the two groups do not overlap:

- Highest in-scope distance: 1.0350
- Lowest out-of-scope distance: 1.0500
- Gap: about 0.0150

This supports a development-set threshold between the two values. However, the gap is narrow and the out-of-scope sample has only four questions. This should not be interpreted as proof that the threshold will generalize.

## 9. Threshold Candidates

Threshold candidates were generated from the observed in-scope and out-of-scope distributions.

| Threshold | TA | FR | TR | FA | In-scope Acceptance | Out-of-scope Rejection |
|---:|---:|---:|---:|---:|---:|---:|
| 0.859163 | 27 | 9 | 4 | 0 | 75.00% | 100.00% |
| 0.901638 | 32 | 4 | 4 | 0 | 88.89% | 100.00% |
| 1.012496 | 34 | 2 | 4 | 0 | 94.44% | 100.00% |
| 1.034999 | 35 | 1 | 4 | 0 | 97.22% | 100.00% |
| 1.042478 | 36 | 0 | 4 | 0 | 100.00% | 100.00% |
| 1.049957 | 36 | 0 | 4 | 0 | 100.00% | 100.00% |
| 1.123829 | 36 | 0 | 3 | 1 | 100.00% | 75.00% |
| 1.263881 | 36 | 0 | 2 | 2 | 100.00% | 50.00% |
| 1.411476 | 36 | 0 | 1 | 3 | 100.00% | 25.00% |

Definitions:

- TA: in-scope accepted
- FR: in-scope rejected
- TR: out-of-scope rejected
- FA: out-of-scope accepted

## 10. False Accept / False Reject Trade-off

False Accept is especially important for fallback because it lets an unsupported query reach generation and increases the opportunity for unsupported generation.

False Reject is also important because it blocks answerable in-scope questions.

In this development set:

- Conservative thresholds such as `0.859163` avoid False Accept but reject many in-scope questions.
- Loose thresholds above `1.123829` begin accepting out-of-scope questions.
- Thresholds between the max in-scope distance and min out-of-scope distance have zero False Accept and zero False Reject on this dev set.

Because the out-of-scope subset has only four questions, the raw counts matter more than percentages.

## 11. Selected Threshold

Selected development-set threshold:

```text
top_1_l2_distance_threshold = 1.042478
```

Decision rule:

```text
top_1_l2_distance <= 1.042478 -> Accept
top_1_l2_distance > 1.042478  -> Fallback
```

Selected-threshold confusion matrix:

| Metric | Count / Rate |
|---|---:|
| True Accept | 36 |
| False Reject | 0 |
| True Reject | 4 |
| False Accept | 0 |
| In-scope Acceptance Rate | 100.00% (36/36) |
| Out-of-scope Rejection Rate | 100.00% (4/4) |
| False Reject Rate | 0.00% (0/36) |
| False Accept Rate | 0.00% (0/4) |

## 12. Selection Rationale

`1.042478` is the midpoint between:

- max in-scope distance: 1.0350
- min out-of-scope distance: 1.0500

It preserves all in-scope questions and rejects all out-of-scope questions on the development set. It is also slightly away from the closest out-of-scope distance, unlike using the exact out-of-scope minimum as the threshold.

This is not an optimal universal threshold. It is a fallback threshold selected from the development set.

## 13. Borderline Queries

Closest queries to the selected threshold:

| id | Scope | Distance | Decision | Top-1 doc |
|---|---|---:|---|---|
| `eval_028` | in-scope | 1.0350 | accept | `aws_alb_monitoring` |
| `eval_040` | out-of-scope | 1.0500 | reject | `k8s_resource_management` |
| `eval_027` | in-scope | 1.0156 | accept | `k8s_secrets` |
| `eval_036` | in-scope | 1.0115 | accept | `aws_vpc_reachability_analyzer` |
| `eval_038` | out-of-scope | 1.1485 | reject | `aws_rds_troubleshooting` |

`eval_040` is the most fragile out-of-scope case because it is only about 0.0075 above the selected threshold.

## 14. Persistent Semantic Misretrieval

Tracked weak questions:

| id | Expected | Top-1 doc | Distance | Decision | Observation |
|---|---|---|---:|---|---|
| `eval_002` | `k8s_debug_running_pod` | `k8s_debug_services` | 0.8658 | accept | wrong top document but confident enough to pass threshold |
| `eval_007` | `k8s_configmaps` | `k8s_secrets` | 0.8747 | accept | ConfigMap/Secrets confusion passes threshold |
| `eval_027` | `k8s_configmaps` | `k8s_secrets` | 1.0156 | accept | borderline-ish but still accepted; ConfigMap/Secrets confusion remains |

Similarity thresholding addresses low-confidence retrieval, but does not necessarily detect high-confidence semantic misretrieval.

## 15. Multi-document Limitation

The threshold signal uses only the Top-1 retrieved chunk distance.

For multi-document questions, the first expected document may be retrieved with high confidence while the second required document is still missing. Therefore, this threshold does not answer:

```text
Did retrieval include all necessary evidence?
```

Multi-document completeness remains a separate retrieval limitation from Phase 10.

## 16. Fallback Implementation

`RagService` now accepts:

```text
distance_threshold: float | None
fallback_answer: str
```

When `distance_threshold` is not set, the service preserves the previous behavior.

When `distance_threshold` is set:

1. retrieve Top-5 chunks
2. inspect rank-1 L2 distance
3. accept if distance is less than or equal to threshold
4. reject if distance is greater than threshold

Fallback response:

```text
I couldn't find sufficient support for this question in the indexed documents.
```

Fallback responses return:

```text
fallback = true
sources = []
retrieved_chunks = retrieved candidates retained for diagnostics
retrieval_distance = rank-1 distance
distance_threshold = selected threshold
```

No unsupported sources are returned as answer sources during fallback.

## 17. LLM Skip Verification

Smoke test results:

| Case | id | Decision | LLM called | Source count |
|---|---|---|---|---:|
| In-scope | `eval_001` | accept | yes | 3 |
| Out-of-scope | `eval_039` | fallback | no | 0 |
| Borderline | `eval_028` | accept | yes | 2 |

The out-of-scope fallback case skipped the LLM call and returned no answer sources.

Unit tests also verify that reject/fallback does not call the LLM client.

## 18. What Threshold Solves

Thresholding can help with:

- Low-confidence unsupported query rejection
- Avoiding unnecessary LLM calls for rejected queries
- Reducing the opportunity for unsupported generation
- Making fallback behavior explicit in the RAG result object

False Accept is not the same as hallucination. False Accept means an unsupported query reaches generation and therefore increases the opportunity for unsupported generation. Actual hallucination must be evaluated later with answer-level evaluation.

## 19. What Threshold Does Not Solve

Thresholding does not solve:

- Wrong document retrieved with high confidence
- ConfigMap / Secrets semantic confusion
- Multi-document evidence completeness
- Duplicate chunk problem
- LLM hallucination itself
- Answer correctness
- Citation correctness

## 20. Limitations

The selected threshold is based only on the development set.

The out-of-scope subset has only four questions. Out-of-scope rejection was 100% (4/4), but one question would change that by 25 percentage points.

The observed separation between in-scope and out-of-scope Top-1 distance is narrow. The nearest in-scope and out-of-scope distances are about 0.015 apart.

Phase 12 freezes the following for Phase 13:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character
embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5
top_1_l2_distance_threshold = 1.042478
```

After Phase 13 uses the held-out test set, these values should not be retuned based on test results.
