# Phase 8 Chunking Experiments

Phase 8 compares character-based chunk size and overlap settings using the development set only.

Held-out test data was not used.

## Fixed Conditions

- Corpus: processed AWS/Kubernetes official documentation from the Phase 5 corpus
- Cleaning: existing Phase 5 processed documents
- Embedding: OpenAI `text-embedding-3-small`
- Vector DB: Chroma
- Retrieval top-k: 3
- Evaluation depth: 10
- Evaluation dataset: `data/evaluation/evaluation_dev.csv`
- LLM generation: not used
- Chunk unit: character

## Compared Settings

| Experiment | Chunk Size | Chunk Overlap | Chunk Count | Overall Hit@1 | Overall Hit@3 | MRR | Multi All-Hit@3 | Mean Latency ms | p95 Latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `chunk_256_0` | 256 | 0 | 1669 | 0.6667 | 0.8889 | 0.7783 | 0.0000 | 137.49 | 161.22 |
| `chunk_256_64` | 256 | 64 | 2217 | 0.6667 | 0.8611 | 0.7743 | 0.1667 | 171.15 | 302.21 |
| `chunk_512_0` | 512 | 0 | 841 | 0.8056 | 0.8889 | 0.8651 | 0.0000 | 131.97 | 154.15 |
| `chunk_512_64` | 512 | 64 | 957 | 0.7778 | 0.8889 | 0.8435 | 0.0000 | 133.92 | 152.15 |
| `chunk_512_128` | 512 | 128 | 1114 | 0.7222 | 0.8889 | 0.8151 | 0.1667 | 130.94 | 151.39 |
| `chunk_1024_128` | 1024 | 128 | 483 | 0.7500 | 0.9167 | 0.8408 | 0.0000 | 132.74 | 153.03 |

## Observed Results

`chunk_1024_128` produced the highest Overall Hit@3 among the six tested settings: 0.9167 (33/36). The baseline `chunk_512_0` measured 0.8889 (32/36). This is a one-question difference on the development in-scope set, not evidence of a statistically generalizable improvement.

The baseline `chunk_512_0` produced the best MRR at 0.8651 and the best Hit@1 at 0.8056. The selected `1024/128` candidate improved Top-3 coverage by one question while reducing rank-1 accuracy and MRR. This is treated as a coverage-ranking trade-off, not as an across-the-board retrieval improvement.

`chunk_1024_128` also had the lowest chunk count at 483. This is a secondary operational observation about embedding/index cost, not proof of retrieval-quality superiority.

The 256-character settings increased chunk count substantially. They did not improve Overall Hit@3, and they reduced MRR. This suggests, but does not prove, that 256-character chunks may lose useful surrounding context for this corpus.

Overlap did not consistently improve retrieval. `256/64` and `512/128` each improved Multi All-Hit@3 from 0.0000 to 0.1667, but both reduced Overall MRR compared with the baseline. `512/64` improved multi-document MRR to 1.0000 but did not improve Multi All-Hit@3.

The larger `1024/128` setting improved Overall Hit@3 but lowered MRR versus the baseline. This means the expected document appeared in the top 3 more often, but not as reliably at rank 1.

## Conceptual and Discrimination Results

| Experiment | Single Conceptual Hit@3 | Single Conceptual MRR | Discrimination Hit@3 | Discrimination MRR |
|---|---:|---:|---:|---:|
| `chunk_256_0` | 0.6000 | 0.5686 | 0.8000 | 0.4619 |
| `chunk_256_64` | 0.4000 | 0.5086 | 0.8000 | 0.4667 |
| `chunk_512_0` | 0.6000 | 0.6786 | 0.8000 | 0.6000 |
| `chunk_512_64` | 0.6000 | 0.5667 | 0.8000 | 0.6667 |
| `chunk_512_128` | 0.6000 | 0.5733 | 0.8000 | 0.7000 |
| `chunk_1024_128` | 0.8000 | 0.7250 | 0.8000 | 0.7000 |

Observed: `1024/128` had the highest `single-conceptual` Hit@3 in this small development subset. Discrimination Hit@3 stayed constant, but MRR improved with larger overlap and larger chunks.

Possible interpretation: conceptual questions may benefit from larger chunks because the relevant explanation has more surrounding context. This is a hypothesis from the current result, not a general rule. Each subset is small, so question-type metrics are diagnostic rather than claims of general superiority.

## Provider Results

| Experiment | Kubernetes Hit@3 | Kubernetes MRR | AWS Hit@3 | AWS MRR |
|---|---:|---:|---:|---:|
| `chunk_256_0` | 0.8421 | 0.7185 | 0.9412 | 0.8451 |
| `chunk_256_64` | 0.8421 | 0.7180 | 0.8824 | 0.8373 |
| `chunk_512_0` | 0.8421 | 0.8684 | 0.9412 | 0.8613 |
| `chunk_512_64` | 0.8421 | 0.8088 | 0.9412 | 0.8824 |
| `chunk_512_128` | 0.8421 | 0.7724 | 0.9412 | 0.8627 |
| `chunk_1024_128` | 0.8421 | 0.7773 | 1.0000 | 0.9118 |

Observed: Kubernetes Hit@3 did not change across settings, but Kubernetes MRR dropped for most non-baseline settings. AWS Hit@3 was highest with `1024/128` in this development set. Provider-level metrics are secondary diagnostics because the AWS and Kubernetes subsets are small.

## Tracked Weak Questions

| Question ID | Baseline Result | Best Observed Change |
|---|---|---|
| `eval_002` | Hit@3 failed for `k8s_debug_running_pod` | No chunking setting fixed top-3 retrieval |
| `eval_007` | Hit@3 failed for `k8s_configmaps`; retrieved Secrets | No chunking setting fixed top-3 retrieval |
| `eval_019` | Hit@3 failed for `aws_vpc_reachability_analyzer` | `1024/128` moved expected doc into rank 2 |
| `eval_027` | Hit@3 failed for `k8s_configmaps`; retrieved Secrets | No chunking setting fixed top-3 retrieval |

Observed: chunking alone did not fix the ConfigMap vs Secret confusion. In the current corpus, evaluation questions, and tested configurations, `eval_007` and `eval_027` repeatedly retrieved Secret documents when ConfigMap was expected. These questions remain in the evaluation set as persistent diagnostic failure cases.

## Multi-Document Observations

All experiments achieved Multi Any-Hit@3 of 1.0000. This means at least one expected document was usually retrievable.

Multi All-Hit@3 remained weak:

- `chunk_256_64`: 0.1667
- `chunk_512_128`: 0.1667
- all others: 0.0000

Tracked multi-document cases showed that top-3 often contained repeated chunks from one document rather than both expected documents. Repeated chunks from the same document are a candidate explanation for low multi-document All-Hit performance, but this is not yet proven. Phase 10 will measure document diversity within Top-k results to test this hypothesis.

## Selected Chunking Candidate

Selected setting for subsequent experiments:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character
```

Selection rationale:

This project prioritized Retrieval Coverage for downstream RAG generation: the relevant source document should appear somewhere in the Top-k context. Under that priority, `1024/128` was selected because it had the highest Overall Hit@3 among the tested settings: 91.67% (33/36).

Secondary observations:

- It improved the previously failing `eval_019` VPC Reachability Analyzer question into top-3.
- It reduced chunk count from 841 to 483, which may reduce embedding/index cost.
- Retrieval latency did not materially worsen in this run.

Trade-off:

`chunk_1024_128` had lower Hit@1 and MRR than the baseline `512/0`. If rank-1 precision or ranking quality is the priority, `512/0` remains attractive. The selected candidate is not a globally optimal chunking configuration; it is the preferred candidate among six tested settings under the current Top-3 coverage priority.

## Phase 10 Follow-Up

Phase 10 should not only compare Hit Rate for k values. It should also measure document diversity inside Top-k results:

- `unique_doc_count`: number of distinct `doc_id` values in Top-k
- `duplicate_chunk_count`: `k - unique_doc_count`
- `duplicate_ratio`: `duplicate_chunk_count / k`
- same-document occupancy inside Top-k
- Multi-document Any-Hit@k
- Multi-document All-Hit@k

Tracked hard cases:

- Service + readiness probe
- ALB + Auto Scaling health check
- RDS + VPC Reachability

## Statistical Caution

The development set has only 40 questions, with 36 in-scope questions. Differences of one or two questions can noticeably move percentages. These results should be treated as directional evidence for Phase 8, not a statistically robust benchmark.

Experiments use sequential tuning rather than an exhaustive joint search across chunking, embedding, and retrieval depth. The selected configuration therefore represents the best candidate among the tested sequential choices, not a guaranteed global optimum.
