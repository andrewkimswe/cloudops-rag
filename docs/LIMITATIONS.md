# Phase 14. Evaluation Limitations

## Summary

This project intentionally uses a controlled, small-scale evaluation workflow. The results are useful for portfolio discussion because they show measurement discipline, trade-off analysis, and honest failure tracking.

They should not be presented as production-scale RAG performance claims.

## Main Limitations

### 1. Small Corpus

The corpus contains 20 official AWS/Kubernetes documents.

This is enough to demonstrate ingestion, retrieval, evaluation, thresholding, and failure analysis, but it is far smaller than a real CloudOps knowledge base.

### 2. Small Evaluation Set

The full evaluation set has 50 manually written questions:

- Development: 40 questions
- Held-out test: 10 questions

The held-out test set has only 8 in-scope questions and 2 out-of-scope questions.

### 3. Small-sample Sensitivity

Held-out in-scope:

```text
1 question = 12.5 percentage points
```

Held-out out-of-scope:

```text
1 question = 50 percentage points
```

Because of this, percentages must always be reported with raw counts.

### 4. Manual Evaluation Dataset

The questions and document-level labels were manually created.

This makes the labels readable and explainable, but it may introduce author bias and does not represent the full diversity of real user questions.

### 5. Domain-specific Corpus

The corpus focuses on AWS and Kubernetes CloudOps troubleshooting. Results should not be generalized to unrelated domains without new evaluation.

### 6. Sequential Tuning

Configuration selection was sequential:

```text
Chunking -> Embedding -> Top-k -> Threshold
```

The project did not search all possible:

```text
Chunking x Embedding x Top-k x Threshold
```

combinations. The frozen final configuration is the result of predefined development-set experiments, not a global optimum.

### 7. Character-based Chunking Only

Chunking experiments used character-based chunk sizes and overlaps.

The project has not yet evaluated token-based chunking, semantic chunking, section-aware chunking, or document-structure-aware chunking.

### 8. Retrieval-focused Evaluation

The current metrics evaluate retrieval:

- Hit@k
- MRR
- Multi-document Any-Hit
- Multi-document All-Hit
- Threshold accept/reject behavior

They do not evaluate:

- Answer correctness
- Faithfulness
- Citation correctness
- Hallucination rate
- LLM-as-a-judge scores
- RAGAS metrics

Do not describe these results as RAG answer accuracy.

### 9. Similarity Threshold Limitation

The Phase 12 threshold uses Top-1 Chroma L2 distance.

It can help reject low-confidence unsupported queries, but it does not reliably detect cases where the retriever confidently returns the wrong semantic neighbor.

For example, ConfigMap questions can retrieve Secrets documents with a distance low enough to pass the threshold.

### 10. Multi-document Completeness

Multi-document retrieval remains the most important weakness.

Development:

- Multi All-Hit@5 = 33.33% (2/6)

Held-out:

- Multi All-Hit@5 = 0.00% (0/3)

The system can often find one relevant document, but it does not reliably retrieve every required evidence document for questions that need multiple sources.

### 11. Duplicate Chunk Diversity

Held-out Top-5 document diversity:

- average unique_doc_count = 2.10
- average duplicate_chunk_count = 2.90
- average duplicate_ratio = 0.58

These results are consistent with the duplicate-chunk hypothesis: repeated chunks from the same document can occupy Top-k positions and reduce document diversity.

This should not be treated as the only cause of multi-document failure. It is evidence consistent with one plausible cause.

### 12. Persistent Semantic Confusion

ConfigMap / Secrets confusion persists across experiments.

This is an example of semantic misretrieval that simple Top-k tuning and distance thresholding do not solve.

### 13. Advanced Retrieval Not Yet Applied

The current frozen final pipeline does not include:

- Maximum Marginal Relevance
- Reranking
- Hybrid search
- BM25
- Document-level deduplication
- Per-document chunk caps
- Query rewriting
- Metadata-aware retrieval
- Semantic chunking
- Token-based chunking

These are future work candidates, not part of the reported final retrieval configuration.

## Recommended Reporting Language

Good:

```text
On the 8 in-scope held-out questions, the frozen configuration retrieved the expected document within Top-3 for 8/8 questions.
```

Good:

```text
Both baseline and final configurations achieved configured-cutoff coverage of 8/8 on the held-out set. The final configuration showed a higher MRR (0.9375 vs 0.8333), but the test set is too small to claim a general ranking improvement.
```

Avoid:

```text
Held-out retrieval accuracy 100%.
```

Avoid:

```text
RAG accuracy 100%.
```

Avoid:

```text
The final configuration significantly improved accuracy.
```

## Future Work

Potential next steps:

- Formal answer-quality evaluation
- Citation correctness checks
- Faithfulness / hallucination evaluation
- MMR or document-diversity retrieval
- Document-level deduplication
- Per-document chunk cap
- Reranking
- Hybrid BM25 + vector retrieval
- Metadata-aware retrieval
- Larger evaluation set
- More realistic user question collection
- Larger AWS/Kubernetes corpus
