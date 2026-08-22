# Phase 11. Final Retrieval Configuration

## 1. Selected Configuration

Final Retrieval Configuration for Phase 12 onward:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character

embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5
```

This is not a global optimal RAG configuration. It is the Final Configuration selected through the project's predefined sequential development-set experiments.

## 2. Selection Process

The configuration was selected through the following development-set sequence:

1. Phase 7 Baseline: `512/0`, OpenAI `text-embedding-3-small`, Chroma, `top_k=3`
2. Phase 8 Chunking: compare character chunk sizes and overlaps, then select `1024/128`
3. Phase 9 Embedding: compare OpenAI `text-embedding-3-small` and `sentence-transformers/all-MiniLM-L6-v2`, then select OpenAI
4. Phase 10 Top-k: compare k=1, k=3, k=5, with k=10 only as diagnostic, then select `top_k=5`

The held-out test set was not used in any of these selection steps.

## 3. Baseline vs Final

Development in-scope question count: 36.

| Configuration | Chunking | Embedding | Top-k | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| Phase 7 Baseline | `512/0` | OpenAI `text-embedding-3-small` | 3 | 80.56% (29/36) | 88.89% (32/36) | not measured | 0.8651 |
| Final ranking before k=5 cutoff | `1024/128` | OpenAI `text-embedding-3-small` | ranking depth 10 | 75.00% (27/36) | 91.67% (33/36) | 91.67% (33/36) | 0.8408 |
| Final Retrieval Configuration | `1024/128` | OpenAI `text-embedding-3-small` | 5 | 75.00% (27/36) | 91.67% (33/36) | 91.67% (33/36) | 0.8408 |

The final configuration does not improve every metric. It prioritizes retrieval coverage and multi-document evidence availability over rank-1 precision and context efficiency.

## 4. Why 1024 / 128

`chunk_size=1024` and `chunk_overlap=128` were selected in Phase 8 because they produced the highest development-set Top-3 document coverage among the tested chunking settings:

- Baseline `512/0`: Hit@3 = 88.89% (32/36)
- Selected `1024/128`: Hit@3 = 91.67% (33/36)

This is a one-question improvement on a small development set, so it should be treated as directional evidence rather than a statistically strong result.

The trade-off is important:

- Hit@1 decreased from 80.56% (29/36) to 75.00% (27/36)
- MRR decreased from 0.8651 to 0.8408

`1024/128` was selected because this project prioritizes having the expected source document somewhere in the retrieved context for downstream RAG generation, not because it has the best rank-1 precision.

## 5. Why OpenAI Embedding

OpenAI `text-embedding-3-small` was selected in Phase 9 because, with `1024/128` fixed, it had stronger overall retrieval coverage than the local MiniLM candidate:

- OpenAI: Hit@3 = 91.67% (33/36), MRR = 0.8408
- MiniLM: Hit@3 = 86.11% (31/36), MRR = 0.8314

OpenAI also showed stronger AWS and discrimination-question results in this development set.

This choice has operational costs:

- It requires an external API call for query embedding.
- It requires an API key.
- It can incur API cost.
- Query latency depends on network and API conditions.

MiniLM remains a valid local/offline alternative, especially if local execution, low latency, or no per-query API dependency becomes more important than development-set Hit@3.

## 6. Why Top-k = 5

k=5 was not selected because it improves overall retrieval accuracy over k=3.

For the final candidate ranking:

- k=3 Overall Hit = 91.67% (33/36)
- k=5 Overall Hit = 91.67% (33/36)

k=5 was selected because it improved multi-document evidence coverage:

- k=3 Multi-document All-Hit = 0.00% (0/6)
- k=5 Multi-document All-Hit = 33.33% (2/6)

For CloudOps troubleshooting questions, some user issues require evidence from more than one document. k=5 surfaced a second expected document in some multi-document cases, so it is a trade-off choice for multi-document evidence availability.

## 7. Coverage vs Ranking Trade-off

Baseline to final candidate:

Advantages:

- Top-3 document coverage improved from 32/36 to 33/36.
- With k=5, Multi-document All-Hit improved from 0/6 to 2/6.
- Some multi-document queries gained access to a second evidence document.

Disadvantages:

- Hit@1 decreased from 80.56% (29/36) to 75.00% (27/36).
- MRR decreased from 0.8651 to 0.8408.
- k=5 increases retrieved context size.
- k=5 increases duplicate same-document chunks in the context.

The final configuration prioritizes retrieval coverage and multi-document evidence availability over rank-1 precision and context efficiency.

## 8. Multi-document Evidence Trade-off

Multi-document retrieval remains the strongest reason for selecting k=5.

| k | Multi Any-Hit | Multi All-Hit |
|---|---:|---:|
| 3 | 100.00% (6/6) | 0.00% (0/6) |
| 5 | 100.00% (6/6) | 33.33% (2/6) |
| 10 diagnostic | 100.00% (6/6) | 50.00% (3/6) |

k=3 usually retrieves at least one relevant document. k=5 sometimes retrieves both required documents.

This benefit is incomplete: k=5 still fails All-Hit for 4 of 6 multi-document questions.

## 9. Context / Duplication Cost

Moving from k=3 to k=5 increases average retrieved context:

| k | Avg Retrieved Chunks | Avg Characters | Approx Tokens | Avg Duplicate Ratio |
|---|---:|---:|---:|---:|
| 3 | 3.0 | 2927.7 | 732.1 | 0.483 |
| 5 | 5.0 | 4941.8 | 1235.6 | 0.605 |

Approximate token count uses `characters / 4`, so it is only a planning estimate.

Phase 10 also showed:

- k=5 average unique doc count: 1.975
- k=5 average duplicate chunks: 3.025
- k=5 duplicate ratio: 0.605

Top-5 retrieval therefore contains only about two distinct documents on average. Phase 10 results provide evidence consistent with the duplicate-chunk hypothesis: repeated chunks from the same document contribute to limited document diversity in multi-document retrieval.

This is not proof that duplicate chunks are the only cause of multi-document failure.

## 10. Remaining Failure Cases

The final configuration does not solve these known weaknesses:

| Area | Remaining Issue |
|---|---|
| Multi-document retrieval | k=5 All-Hit is 2/6, so 4/6 multi-document questions still miss at least one required document. |
| Service + readiness probe | `eval_021` still misses the second expected document, `k8s_debug_services`, even at k=5. |
| RDS + VPC Reachability | `eval_024` still misses the second expected document, `aws_vpc_reachability_analyzer`, even at k=5. |
| ConfigMap vs Secrets | `eval_007` and `eval_027` continue to retrieve Secrets content ahead of ConfigMaps content. |
| Ranking quality | Hit@1 and MRR are lower than the Phase 7 baseline. |

These cases should remain in the evaluation set. They are useful diagnostic failures, not questions to remove.

## 11. Limitations

This configuration was selected on the development set only.

The development set is small:

- Total dev questions: 40
- In-scope dev questions: 36
- Multi-document questions: 6

One in-scope question changes Hit Rate by about 2.78 percentage points, so small differences should not be overinterpreted.

The selection process was sequential:

```text
Chunking -> Embedding -> Top-k
```

It was not an exhaustive search across all:

```text
Chunking x Embedding x Top-k
```

combinations. Final Configuration refers to the configuration selected through the project's predefined sequential development-set experiments.

## 12. What Is Frozen From This Point

For Phase 12 and Phase 13, freeze:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character

embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5
```

After the held-out test set is opened in the original plan, do not change:

- Chunking
- Embedding model
- Top-k

k=10 is not part of the Final Retrieval Configuration. k=10 was used only as a diagnostic cutoff to inspect whether missing relevant documents existed deeper in the ranking.

The following are not part of the Final Retrieval Configuration:

- Maximum Marginal Relevance
- Document-level deduplication
- Per-document chunk cap
- Hybrid Search
- BM25
- Reranker
- Query Rewriting
- Metadata-aware Retrieval
- Similarity Threshold / Fallback

Future advanced retrieval experiments should be documented separately from this frozen final retrieval pipeline.
