# Phase 14. Evaluation Summary

## Scope

This document summarizes the retrieval and fallback evaluation from Phase 7 through Phase 13.

It is a retrieval-focused evaluation summary, not an answer-quality benchmark. It should be used in README and portfolio material with raw counts and limitations preserved.

## Frozen Final Configuration

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

This configuration was selected through sequential development-set experiments. It is not claimed to be a global optimum.

## Dataset Scale

| Split | Total Questions | In-scope | Out-of-scope |
|---|---:|---:|---:|
| Development | 40 | 36 | 4 |
| Held-out Test | 10 | 8 | 2 |
| Total | 50 | 44 | 6 |

The corpus contains 20 official AWS/Kubernetes CloudOps and troubleshooting documents.

## Development Summary

The Phase 7 baseline used:

```text
chunk_size = 512
chunk_overlap = 0
embedding_model = OpenAI text-embedding-3-small
top_k = 3
```

Development baseline:

- Hit@1 = 80.56% (29/36)
- Hit@3 = 88.89% (32/36)
- MRR = 0.8651

The frozen final candidate on development:

- Hit@1 = 75.00% (27/36)
- Hit@3 = 91.67% (33/36)
- Hit@5 = 91.67% (33/36)
- MRR = 0.8408
- Multi-document All-Hit@5 = 33.33% (2/6)

The development result shows a trade-off: the final configuration improved configured-context coverage and some multi-document evidence availability, but reduced Hit@1 and MRR compared with the baseline.

## Held-out Test Summary

Held-out test set:

- Total questions: 10
- In-scope: 8
- Out-of-scope: 2

Frozen final retrieval on held-out in-scope questions:

| Metric | Result |
|---|---:|
| Hit@1 | 87.50% (7/8) |
| Hit@3 | 100.00% (8/8) |
| Hit@5 | 100.00% (8/8) |
| MRR | 0.9375 |

Preferred portfolio wording:

> On the 8 in-scope held-out questions, the frozen configuration retrieved the expected document within Top-3 for 8/8 questions.

Avoid wording such as:

- Held-out retrieval accuracy 100%
- RAG accuracy 100%
- The final configuration greatly improved accuracy

## Single-document Results

Held-out single-document retrieval:

| Metric | Result |
|---|---:|
| Hit@1 | 100.00% (5/5) |
| Hit@3 | 100.00% (5/5) |
| Hit@5 | 100.00% (5/5) |
| MRR | 1.0000 |

Single-document retrieval worked well in the held-out set, but the subset contains only five questions.

## Multi-document Results

Development:

- Multi Any-Hit@5 = 100.00% (6/6)
- Multi All-Hit@5 = 33.33% (2/6)

Held-out:

- Multi Any-Hit@3 = 100.00% (3/3)
- Multi Any-Hit@5 = 100.00% (3/3)
- Multi All-Hit@3 = 0.00% (0/3)
- Multi All-Hit@5 = 0.00% (0/3)

Interpretation:

The retriever often finds one relevant document, but it does not reliably retrieve all required evidence documents for multi-document CloudOps troubleshooting questions. This limitation repeated in the held-out set.

## Threshold / Fallback Summary

Frozen threshold:

```text
Top-1 L2 distance <= 1.042478 -> Accept
Top-1 L2 distance > 1.042478  -> Reject / Fallback
```

Held-out threshold result:

| Metric | Result |
|---|---:|
| True Accept | 8 |
| False Reject | 0 |
| True Reject | 2 |
| False Accept | 0 |
| In-scope Acceptance | 100.00% (8/8) |
| Out-of-scope Rejection | 100.00% (2/2) |

This result is encouraging, but the out-of-scope held-out subset has only two questions. One out-of-scope question would change this rate by 50 percentage points.

## Baseline vs Final on Held-out Test

| Metric | Original Baseline | Frozen Final |
|---|---:|---:|
| Configured-cutoff coverage | 100.00% (8/8) | 100.00% (8/8) |
| Hit@1 | 75.00% (6/8) | 87.50% (7/8) |
| MRR | 0.8333 | 0.9375 |
| Multi All-Hit at configured cutoff | 0.00% (0/3) | 0.00% (0/3) |

Both baseline and final configurations achieved configured-cutoff coverage of 8/8 on the held-out set. The final configuration showed a higher MRR (0.9375 vs 0.8333), but the test set is too small to claim a general ranking improvement.

## What Worked

- Single-document retrieval was strong on the held-out set.
- The frozen final configuration retrieved an expected document within Top-3 for all 8 in-scope held-out questions.
- The development-selected threshold rejected both held-out out-of-scope questions.
- The project now has a source-aware RAG pipeline with fallback behavior.
- The evaluation workflow separates development selection from held-out validation.

## What Remains Weak

- Multi-document completeness remains weak.
- ConfigMap / Secrets semantic confusion remains visible.
- Duplicate chunks limit Top-k document diversity.
- Similarity thresholding does not detect high-confidence semantic misretrieval.
- LLM answer quality has not yet been formally evaluated.

## Final Interpretation

The evaluation supports a cautious conclusion:

The frozen retrieval configuration works reasonably well for single-document retrieval and basic out-of-scope fallback in this small AWS/Kubernetes troubleshooting corpus. However, multi-document evidence retrieval remains the main unresolved weakness, and the dataset is too small to make broad claims about production performance.
