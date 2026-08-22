# Phase 9 Embedding Experiments

Phase 9 compares the two embedding candidates selected in `docs/DECISIONS.md`.

Held-out test data was not used.

## Fixed Conditions

- Corpus: same 20 processed AWS/Kubernetes official documents
- Chunking: `chunk_size=1024`, `chunk_overlap=128`
- Chunk unit: character
- Vector DB: Chroma
- Retrieval top-k: 3
- Evaluation depth: 10
- Dataset: `data/evaluation/evaluation_dev.csv`
- LLM generation: not used

## Compared Models

| Experiment | Model | Type | Dimension | Chunk Count | Collection |
|---|---|---|---:|---:|---|
| `openai_text_embedding_3_small` | `text-embedding-3-small` | API | 1536 | 483 | `cloudops_rag_v1_embedding_openai_text_embedding_3_small` |
| `local_all_minilm_l6_v2` | `sentence-transformers/all-MiniLM-L6-v2` | Local | 384 | 483 | `cloudops_rag_v1_embedding_local_all_minilm_l6_v2` |

MiniLM was executed locally with `sentence-transformers==6.0.0`, `transformers==5.15.1`, and `torch==2.13.0`.

MiniLM is an optional local experiment dependency, not a default Docker runtime dependency. Install it only when reproducing the local embedding experiment:

```bash
python -m pip install ".[local]"
```

## Summary Results

| Experiment | Hit@1 | Hit@3 | MRR | Single Hit@3 | Multi Any@3 | Multi All@3 | Mean Query Latency ms | p95 Query Latency ms | Indexing Time ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `openai_text_embedding_3_small` | 0.7500 | 0.9167 | 0.8408 | 0.9000 | 1.0000 | 0.0000 | 185.60 | 342.59 | 7143.32 |
| `local_all_minilm_l6_v2` | 0.7778 | 0.8611 | 0.8314 | 0.8333 | 1.0000 | 0.1667 | 4.71 | 11.36 | 5096.25 |

Observed:

- OpenAI had better Overall Hit@3 and slightly better MRR.
- MiniLM had better Hit@1, much lower query latency, and one successful Multi All-Hit@3 case.
- OpenAI had stronger AWS subset results in this development set.
- MiniLM had stronger Kubernetes MRR in this development set but not higher Kubernetes Hit@3.

Do not compare raw distance values across these models. Their embedding spaces and distance distributions are different.

## Question Type Results

| Experiment | Question Type | Hit@1 | Hit@3 | MRR |
|---|---|---:|---:|---:|
| OpenAI | single-conceptual | 0.6000 | 0.8000 | 0.7250 |
| OpenAI | discrimination | 0.6000 | 0.8000 | 0.7000 |
| OpenAI | multi-document | 0.8333 | 1.0000 | 0.9167 |
| MiniLM | single-conceptual | 0.6000 | 0.8000 | 0.7000 |
| MiniLM | discrimination | 0.4000 | 0.6000 | 0.5139 |
| MiniLM | multi-document | 1.0000 | 1.0000 | 1.0000 |

Observed:

- Conceptual Hit@3 was tied.
- OpenAI had better discrimination-question results in this small development subset.
- MiniLM ranked at least one relevant multi-document source at rank 1 for all multi-document questions.

Question-type metrics are diagnostic and should not be generalized because each subset contains only a small number of questions.

## Provider Results

| Experiment | Provider | Hit@1 | Hit@3 | MRR |
|---|---|---:|---:|---:|
| OpenAI | Kubernetes | 0.6842 | 0.8421 | 0.7773 |
| OpenAI | AWS | 0.8235 | 1.0000 | 0.9118 |
| MiniLM | Kubernetes | 0.7895 | 0.8421 | 0.8282 |
| MiniLM | AWS | 0.7647 | 0.8824 | 0.8350 |

Observed:

- OpenAI performed better on AWS questions in this development subset.
- MiniLM improved Kubernetes ranking quality in this development subset but did not improve Kubernetes Hit@3.

Provider-level metrics are diagnostic rather than general claims about model behavior.

## Tracked Weak Questions

| Question | OpenAI Result | MiniLM Result | Observation |
|---|---|---|---|
| `eval_002` expected `k8s_debug_running_pod` | Hit@3 failed | Hit@3 failed | Embedding change did not fix this question |
| `eval_007` expected `k8s_configmaps` | Hit@3 failed; retrieved Secrets | Hit@3 failed; retrieved Secrets | ConfigMap vs Secret confusion remains |
| `eval_019` expected `aws_vpc_reachability_analyzer` | Hit@3 success at rank 2 | Hit@3 success at rank 2 | Phase 8 improvement remains with both models |
| `eval_027` expected `k8s_configmaps` | Hit@3 failed; retrieved Secrets | Hit@3 failed; retrieved Secrets | ConfigMap discrimination remains unresolved |

## Multi-Document Hard Cases

| Case | OpenAI Top-3 | MiniLM Top-3 | Observation |
|---|---|---|---|
| Service + readiness probe `eval_021` | probes, probes, HPA | probes, debug pods, debug running pod | MiniLM diversified documents more, but still missed `k8s_debug_services` |
| ALB + Auto Scaling health `eval_023` | unhealthy instances, health checks, health checks | health checks, health checks, unhealthy instances | Both found Auto Scaling side but missed ALB in top-3 |
| RDS + VPC Reachability `eval_024` | RDS, RDS, RDS | RDS, RDS, RDS | Both failed to include Reachability Analyzer in top-3 |

Observed:

MiniLM improved Multi All-Hit@3 from 0.0000 to 0.1667 overall, but the tracked hard cases still show repeated chunks from one document dominating top-3. Repeated same-document chunks are a candidate explanation, not a proven root cause. Phase 10 should measure document diversity before introducing retrieval diversification techniques.

## API vs Local Trade-Off

### OpenAI `text-embedding-3-small`

- Retrieval quality: stronger Overall Hit@3 and AWS performance in this experiment.
- Query latency: higher because each query embedding requires an API call.
- Indexing latency: measured at 7143.32 ms for 483 chunks in this run.
- API cost: yes, cost can occur; exact cost was not calculated in this phase.
- External dependency: requires internet/API availability.
- API key: required.
- Local execution: no.

### `sentence-transformers/all-MiniLM-L6-v2`

- Retrieval quality: lower Overall Hit@3 but competitive MRR and better Multi All-Hit@3 in this experiment.
- Query latency: much lower after model load because embedding runs locally.
- Indexing latency: measured at 5096.25 ms for 483 chunks in this run.
- API cost: no per-query API cost.
- External API dependency: no after model download.
- API key: not required.
- Local execution: yes.
- Offline execution: possible after model artifacts are downloaded.

In this experiment environment, MiniLM showed approximately 39x lower mean query embedding latency than the OpenAI API-based embedding: 185.60 ms / 4.71 ms. This value is environment-dependent and should not be interpreted as a general model-level performance ratio.

## Selected Embedding

Selected for the next phase candidate:

```text
OpenAI text-embedding-3-small
```

Rationale:

1. It had the best Overall Hit@3, which is the first selection priority.
2. It had slightly better MRR than MiniLM.
3. It had stronger AWS subset results in this development set.
4. It had stronger discrimination subset results in this development set.

Trade-off:

MiniLM is not simply a rejected lower-quality model. It is operationally attractive: local execution, no API key, no per-query external API cost, offline execution after download, and much lower query embedding latency in this experiment environment. MiniLM also improved Multi All-Hit@3 in this small dev set. If local/offline operation becomes more important than Overall Hit@3, MiniLM remains a strong candidate.

## Statistical Caution

The development set has 40 questions and 36 in-scope questions. A one-question difference changes Hit@3 by about 2.78 percentage points on in-scope evaluation. These results should be treated as directional evidence, not a statistically robust benchmark.

These experiments use sequential tuning. Chunking was selected first, then embedding was compared under the selected chunking candidate. This is a practical approach for a personal project, but it does not guarantee a global optimum across all chunking and embedding combinations.
