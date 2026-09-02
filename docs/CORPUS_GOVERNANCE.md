# Corpus Governance

## Goal

CloudOps RAG uses a narrow official-document corpus so retrieval labels can stay meaningful and source quality can be defended in interviews.

## Source Policy

Accepted sources:

- official AWS documentation
- official Kubernetes documentation
- CloudOps, operations, observability, service, networking, autoscaling, and troubleshooting pages

Excluded sources:

- blog posts
- forum answers
- vendor summaries
- copied credentials or private operational notes
- unofficial mirrors of official docs

## Manifest Fields

The source inventory is managed in `data/manifests/documents.csv`.

Important fields:

- `doc_id`: stable human-readable identifier used as retrieval ground truth
- `title`: document title used in source display
- `provider`: bounded provider label such as `aws` or `kubernetes`
- `category`: troubleshooting category
- `source_url`: canonical official documentation URL
- `status`: corpus registration state
- `local_path`: local fetched/processed path when available

`doc_id` values should not change once evaluation labels reference them.

## Adding a Document

When adding a document:

1. Add a manifest row with a stable `doc_id`.
2. Confirm the `source_url` is an official AWS or Kubernetes URL.
3. Fetch and process the document.
4. Rebuild the target Chroma collection.
5. Check whether existing evaluation labels need to change.
6. Add or update evaluation questions only in the appropriate phase/workflow.
7. Re-run retrieval evaluation and compare against regression gates.
8. Update docs only after metrics are available.

## Evaluation Label Impact

Ground truth uses `doc_id`, not `chunk_id`.

This is intentional because chunk boundaries can change when chunk size or overlap changes. `doc_id` labels remain stable across chunking experiments.

Corpus changes may affect evaluation in two directions:

- A new document can become a better expected source for an existing question.
- A removed or renamed document can invalidate existing labels.

Both cases require explicit evaluation review before making new performance claims.

## Evaluation vs Runtime Collections

Evaluation Chroma and runtime Chroma are separated:

- evaluation collection: frozen, reproducible, tied to reported metrics
- runtime collection: mutable, used by API document ingestion

This prevents runtime document additions from silently changing reported evaluation results.

## Re-evaluation Triggers

Re-run evaluation when changing:

- corpus membership
- `doc_id` values
- document parsing/cleaning behavior
- chunk size or overlap
- embedding model
- retrieval top-k
- threshold
- source filtering
- reranking, diversification, MMR, hybrid search, or query rewriting

## Current Corpus Scope

The current v1 corpus contains 20 official AWS/Kubernetes troubleshooting and CloudOps documents. It is sufficient for a focused portfolio project, but too small to support broad claims about general CloudOps coverage.
