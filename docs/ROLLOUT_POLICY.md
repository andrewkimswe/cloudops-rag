# Rollout Policy

## Goal

This project should not promote retrieval, generation, model, threshold, or corpus changes directly from implementation to public claims.

The expected flow is:

```text
retriever/model/chunking change
-> development evaluation
-> held-out validation
-> diagnostic answer evaluation
-> canary
-> full rollout
```

## Change Types That Need Rollout Discipline

- Chunk size or chunk overlap changes.
- Embedding model changes.
- Chroma collection changes.
- Retrieval top-k changes.
- Similarity threshold changes.
- Prompt or generation model changes.
- Corpus additions/removals.
- Retrieval diversification, reranking, MMR, hybrid search, or query rewriting.

## Evaluation Sequence

1. Development evaluation

   Run retrieval evaluation on the development split. Use this for iteration and diagnosis.

2. Held-out validation

   Run held-out evaluation only after selecting a candidate. Do not tune on held-out failures.

3. Diagnostic answer evaluation

   Generate answers for a small diagnostic set and evaluate correctness, completeness, faithfulness, and source support.

4. Canary

   Route a small portion of real or manually simulated traffic to the candidate configuration. Compare behavior against the frozen configuration.

5. Full rollout

   Promote only after the candidate passes retrieval, answer-quality, latency, cost, and fallback guardrails.

## Rollout Guardrails

Monitor these signals before promotion:

- fallback rate increase
- p95 query latency increase
- p95 generation latency increase
- OpenAI timeout or failure increase
- answer correctness decrease
- answer completeness decrease
- source support decrease
- multi-document completeness decrease
- retrieval regression gate failure

## Rollback Policy

Rollback should be immediate when:

- the regression gate fails
- fallback rate spikes without an expected corpus/query mix change
- OpenAI failure rates rise after a code/config change
- source support or faithfulness drops in diagnostic review
- latency exceeds the current synchronous service budget

Rollback should restore the last frozen configuration and its matching Chroma collection.

## Current v1 Status

The current frozen configuration remains:

```text
chunk_size = 1024
chunk_overlap = 128
embedding = OpenAI text-embedding-3-small
vector DB = Chroma
retrieval_top_k = 5
threshold = 1.042478
generation = gpt-4o-mini
```

The post-hoc cap=2 diversification result is a candidate only. It is not part of the frozen production path until evaluated on a new untouched validation set.
