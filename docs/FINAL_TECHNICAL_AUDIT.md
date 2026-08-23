# Final Technical Audit

## 1. Scope

This audit reviews service failure handling, metric consistency, result/documentation consistency, and portfolio-safe claim boundaries after Phase 18 Monitoring. It does not rerun retrieval experiments, regenerate answers, rerun the judge, change human scores, retune threshold, change prompts, or apply the post-hoc cap=2 diversification candidate to production.

Frozen production configuration remains:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character
embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5
threshold = 1.042478
generation_model = gpt-4o-mini
```

The post-hoc per-document chunk cap of 2 remains candidate-only.

## 2. Service Failure Handling

OpenAI timeout configuration is explicit:

| Operation | Timeout | Location |
|---|---:|---|
| Query embedding | 30s | `DEFAULT_OPENAI_EMBEDDING_TIMEOUT_SECONDS` |
| Runtime document embedding | 30s | same `OpenAIEmbedder` client |
| Answer generation | 45s | `DEFAULT_OPENAI_LLM_TIMEOUT_SECONDS` |
| Judge calls | experiment script only | not used by production API |

OpenAI SDK exceptions are normalized at the client boundary:

| Failure | Internal exception | API response | Metric |
|---|---|---|---|
| Embedding timeout | `TimeoutError` | `504 external_dependency_timeout` | `cloudops_rag_openai_failures_total{operation="embedding"}` |
| Embedding non-timeout failure | `RuntimeError` | `503 external_dependency_unavailable` | `cloudops_rag_openai_failures_total{operation="embedding"}` |
| Generation timeout | `TimeoutError` | `504 external_dependency_timeout` | `cloudops_rag_openai_failures_total{operation="generation"}` |
| Generation non-timeout failure | `RuntimeError` | `503 external_dependency_unavailable` | `cloudops_rag_openai_failures_total{operation="generation"}` |

Generation failures happen after retrieval has succeeded, but the API intentionally returns an error response rather than a partial answer or sources-only response. This keeps the service contract simple: fallback is a successful controlled response, failure is an error response.

Current retry policy: no application-level retry/backoff. The OpenAI SDK may apply its own retry behavior, but this project does not add another retry layer. That is appropriate for the current portfolio-scale synchronous API because blind retries could increase latency/cost and should distinguish 429/transient 5xx from invalid request/authentication failures. Future production hardening can add bounded retries for retryable timeout/429/5xx only.

## 3. Ingestion Failure Handling

Runtime ingestion lifecycle remains:

```text
pending -> processing -> completed
failed
```

Failure handling by stage:

| Stage | Failure examples | Stored error code | Partial-state behavior |
|---|---|---|---|
| fetch | timeout | `fetch_timeout` | failed status saved |
| fetch | URL/open failure | `fetch_failed` | failed status saved |
| parse | unsupported/invalid content | `invalid_content` or `parsing_failed` | failed status saved |
| chunk | no chunks / too little text | `parsing_failed` | failed status saved |
| embed | OpenAI embedding failure | `embedding_failed` | same-doc chunks cleaned |
| index | Chroma upsert/count mismatch/failure | `indexing_failed` | same-doc chunks cleaned |

Stable runtime `doc_id` values and same-doc chunk deletion make retry practical for this single-process service. This is not a distributed transaction guarantee, but it prevents obvious duplicate/partial chunk buildup for the same document.

## 4. HTTP Error Consistency

All audited API error paths use:

```json
{
  "error": {
    "code": "...",
    "message": "..."
  }
}
```

Validation errors are normalized by the FastAPI `RequestValidationError` handler to `422 invalid_request`. Document status misses return `404 document_not_found`. Query dependency failures return `503` or `504`. Unexpected exceptions return `500 internal_error`.

Logging avoids API keys, full questions, answers, source content, document URLs, and exception messages as metric labels. Existing error logging records stack traces server-side; metric labels remain bounded.

## 5. Metric Definitions

Retrieval metrics use document-level ground truth. `expected_chunk` is intentionally absent because chunk boundaries change across chunking experiments.

Definitions:

| Metric | Definition |
|---|---|
| Hit@k | At least one expected `doc_id` appears within rank k. |
| MRR | Reciprocal rank of the first expected `doc_id`; 0 if absent within the evaluated ranking depth. |
| Multi Any-Hit@k | At least one expected `doc_id` appears within rank k. |
| Multi All-Hit@k | All expected `doc_id` values appear within rank k. |

## 6. MRR Consistency

The observed MRR discrepancy is explained by different ranking depths used for reciprocal-rank calculation.

| Result family | Ranking used for MRR | Overall MRR | Single MRR | Multi MRR |
|---|---|---:|---:|---:|
| Phase 7 baseline `512/0`, k=3 | raw depth 10 | 0.8651 | 0.8548 | 0.9167 |
| Phase 8 selected `1024/128`, k=3 | raw depth 10 | 0.8408 | 0.8256 | 0.9167 |
| Phase 9 OpenAI `1024/128`, k=3 | raw depth 10 | 0.8408 | 0.8256 | 0.9167 |
| Phase 10 final k=5 | raw depth 10 | 0.8408 | 0.8256 | 0.9167 |
| Diversification baseline | final Top-5 only | 0.8333 | 0.8167 | 0.9167 |
| Diversification cap=2 | final Top-5 only | 0.8426 | 0.8278 | 0.9167 |

Rows causing the `0.8408` vs `0.8333` difference:

| ID | Expected doc | Raw-depth MRR | Top-5-only MRR | Explanation |
|---|---|---:|---:|---|
| `eval_002` | `k8s_debug_running_pod` | 1/7 | 0 | expected doc is below Top-5. |
| `eval_007` | `k8s_configmaps` | 1/8 | 0 | expected doc is below Top-5 before cap=2. |

Conclusion: Hit@k values are consistent; MRR values are not contradictory, but they must be reported with their evaluated depth. Portfolio/README language should avoid comparing raw-depth MRR and Top-5-only MRR as if they were identical definitions.

## 7. Retrieval Result Validation

Frozen Dev raw counts:

| Metric | Count |
|---|---:|
| Hit@1 | 27/36 |
| Hit@3 | 33/36 |
| Hit@5 | 33/36 |
| Multi Any-Hit@5 | 6/6 |
| Multi All-Hit@5 | 2/6 |

Held-out frozen final counts:

| Metric | Count |
|---|---:|
| In-scope questions | 8 |
| OOS questions | 2 |
| Hit@1 | 7/8 |
| Hit@3 | 8/8 |
| Hit@5 | 8/8 |
| MRR | 0.9375 |
| Single all cutoffs | 5/5 |
| Multi Any-Hit@3/5 | 3/3 |
| Multi All-Hit@3/5 | 0/3 |

Diversification Dev counts:

| Variant | Hit@1 | Hit@3 | Hit@5 | Multi Any-Hit@5 | Multi All-Hit@5 |
|---|---:|---:|---:|---:|---:|
| Baseline | 27/36 | 33/36 | 33/36 | 6/6 | 2/6 |
| cap=2 candidate | 27/36 | 34/36 | 34/36 | 6/6 | 4/6 |

## 8. Diversification Controlled Experiment

The diversification experiment used one raw Top-20 retrieval per Dev question. Baseline is `raw[:5]`; cap=2 is a post-processing selection from the same raw Top-20 ranking. No generation or judge calls were used.

Important cases:

| ID | Observation |
|---|---|
| `eval_007` | cap=2 promoted `k8s_configmaps` into Top-5 by limiting repeated `k8s_secrets` chunks. |
| `eval_022` | cap=2 added missing `k8s_debug_pods`; in raw ranking it first appeared at rank 9. |
| `eval_024` | cap=2 added missing `aws_vpc_reachability_analyzer`; in raw ranking it first appeared at rank 20. |
| `eval_027` | cap=2 still did not retrieve `k8s_configmaps`; this remains ConfigMap/Secrets confusion. |
| `eval_043` | cap=2 brought both `k8s_secrets` and `k8s_configmaps` into Top-5. |
| `eval_046` | cap=2 did not recover `aws_vpc_reachability_analyzer`. |

Conclusion: duplicate occupancy is supported as a partial cause of multi-document failure, not the only cause. cap=2 remains candidate-only.

## 9. Threshold Validation

Threshold semantics:

```text
Chroma distance field = L2
lower distance = more similar
accept if top_1_l2_distance <= 1.042478
fallback if top_1_l2_distance > 1.042478
```

Dev threshold result: 36 true accepts, 0 false rejects, 4 true rejects, 0 false accepts.

Held-out threshold result: 8 true accepts, 0 false rejects, 2 true rejects, 0 false accepts.

Limitation: the threshold rejects unsupported low-confidence queries, but it does not detect high-confidence semantic misretrieval. `eval_027` is the clearest example: Secret-centered context passed threshold for a ConfigMap-focused question.

The threshold is corpus- and sample-dependent. It should not be described as a production-general threshold.

## 10. Answer Evaluation Validation

Diagnostic answer evaluation raw counts:

| Item | Count |
|---|---:|
| Diagnostic questions | 14 |
| Generated answers | 11 |
| Fallback rows | 3 |
| Fallback correctness | 14/14 deterministic expectation check; 3/3 actual fallback rows |
| Answerable source Any-Hit | 10/11 |
| Answerable source All-Hit | 7/11 |
| Multi-source All-Hit | 0/3 |

Human scores over 11 generated answers:

| Dimension | Distribution | Mean |
|---|---|---:|
| Correctness | 6 score2, 3 score1, 2 score0 | 1.3636 |
| Completeness | 4 score2, 5 score1, 2 score0 | 1.1818 |
| Faithfulness | 10 score2, 1 score1, 0 score0 | 1.9091 |
| Source Support | 8 score2, 2 score1, 1 score0 | 1.6364 |

Judge-human agreement over 44 score assignments: 39/44 exact and 44/44 within one point.

Human final failure types over 11 generated answers:

| Failure type | Count |
|---|---:|
| no_material_failure | 4 |
| retrieval_failure | 1 |
| generation_failure | 4 |
| combined_failure | 2 |

Notable answer cases:

| ID | Audit finding |
|---|---|
| `eval_027` | Human correctness 0, faithfulness 2, source support 0. The answer stayed faithful to retrieved Secret-centered evidence, but that evidence did not answer the ConfigMap question. |
| `eval_043` | Partial source retrieval led to partial answer quality; ConfigMap support was incomplete. |
| `eval_045` | Exact expected `aws_ec2_autoscaling_health_checks` was absent, but alternative Auto Scaling unhealthy-instance evidence supported the answer; document-level retrieval miss did not imply answer-level unsupportedness. |
| `eval_046` | RDS context dominated; VPC Reachability Analyzer evidence was missing, reducing completeness. |

## 11. Data Split / Leakage Policy

Retrieval tuning used the Development set. Held-out Test was opened after freezing chunking, embedding, Top-k, and threshold. No retuning was performed after held-out results.

Answer Quality Evaluation reused a small diagnostic subset of existing evaluation questions and is not a benchmark.

Diversification was post-hoc on the Development set only. The existing held-out set was not reused to validate cap=2, and cap=2 was not promoted to production.

Sequential tuning remains a limitation: chunking, embedding, Top-k, and threshold were selected sequentially, not through a global search.

## 12. Performance Assessment

| Area | Rating | Reason |
|---|---|---|
| Single-document Retrieval | Good | Held-out single questions succeeded 5/5 at all cutoffs. |
| Multi-document Retrieval | Weak | Dev All-Hit@5 = 2/6 and held-out All-Hit@5 = 0/3. |
| Ranking Quality | Acceptable | Held-out MRR = 0.9375, but Dev final MRR is lower than Phase 7 baseline and sample sizes are small. |
| Out-of-scope Detection | Acceptable | Dev 4/4 and held-out 2/2 rejected, but OOS sample is tiny. |
| Answer Correctness | Acceptable | Human mean 1.3636/2 on 11 generated answers; diagnostic only. |
| Answer Completeness | Weak | Human mean 1.1818/2; multi-document missing evidence is visible. |
| Faithfulness / Groundedness | Good | Human mean 1.9091/2, but faithfulness to wrong context can still be incorrect. |
| Source Support | Acceptable | Human mean 1.6364/2 with one score0 case. |
| API Reliability | Acceptable | Consistent error envelopes, timeout mapping, and failure metrics now covered by tests. |
| Runtime Ingestion | Acceptable | Synchronous lifecycle, duplicate handling, cleanup, and failure statuses are tested. |
| Docker / Reproducibility | Good | Python 3.12 Docker runtime, healthcheck, metrics smoke validated. |
| Monitoring | Good | Prometheus `/metrics` covers HTTP/query/stage/fallback/ingestion/failure metrics with bounded labels. |

## 13. Supported Claims

Strongly supported claims:

- Built an end-to-end FastAPI RAG service over AWS/Kubernetes troubleshooting docs.
- Used document-level retrieval evaluation with Hit@k, MRR, Multi Any-Hit, and Multi All-Hit.
- Froze a configuration before held-out validation.
- On 8 held-out in-scope questions, the frozen configuration retrieved an expected document within Top-3 for 8/8 questions.
- Implemented threshold fallback that skips generation when top-1 L2 distance exceeds the selected threshold.
- Added runtime ingestion, Docker packaging, and Prometheus application metrics.
- Found and documented multi-document completeness as a persistent weakness.

Supported with caveat:

- Held-out MRR improved versus original baseline: 0.9375 vs 0.8333, but only 8 in-scope held-out questions.
- OOS rejection worked on Dev 4/4 and held-out 2/2, but the OOS sample is extremely small.
- Judge-human agreement was 39/44 exact and 44/44 within one point, but only over 11 generated answers.
- cap=2 improved Dev Multi All-Hit@5 from 2/6 to 4/6, but it is post-hoc Dev-only and not production.

Claims to avoid:

- “RAG accuracy is 100%.”
- “Production-ready OOS detection.”
- “The final configuration generally improves accuracy.”
- “The threshold prevents hallucination or semantic misretrieval.”
- “cap=2 is validated for production.”
- “Answer quality is comprehensively benchmarked.”

## 14. Resume-Friendly Quantitative Figures

| Figure | Use? | Required caveat |
|---|---|---|
| Held-out expected-document Top-3 = 8/8 | Yes | 8 in-scope held-out questions only. |
| Held-out MRR = 0.9375 | Yes | Ranking metric on 8 in-scope held-out questions; not broad benchmark. |
| Dev Multi All-Hit@5 = 2/6; held-out = 0/3 | Yes | Present as limitation, not success. |
| cap=2 Dev Multi All-Hit@5 = 2/6 -> 4/6 | Yes | Post-hoc Dev-only candidate, not production. |
| Judge-human exact agreement = 39/44 | Yes | Agreement on 11 generated diagnostic answers, not answer accuracy. |
| Human faithfulness mean = 1.9091/2 | Maybe | Faithfulness can be high even when retrieved context is wrong. |
| OOS rejection Dev 4/4, held-out 2/2 | Maybe | Very small OOS sample; avoid production-general claim. |

## 15. README Numeric Cross-check

Key README values were cross-checked against raw result files. No numeric mismatch was found for the audited core values: frozen config, Dev Hit@k/MRR, held-out Hit@k/MRR, threshold confusion matrix, answer diagnostic counts, judge-human agreement, multi-document limitation counts, and diversification candidate counts.

One interpretive nuance: MRR in Phase 8/9/10/final docs is raw-depth-10 MRR, while diversification MRR is final-Top-5 MRR. Both are internally correct, but they should not be compared without naming the depth difference.

## 16. Remaining Risks

- Corpus has only 20 official documents.
- Retrieval evaluation has only 50 questions.
- Held-out Test has only 10 questions.
- OOS evaluation is especially small.
- Multi-document completeness remains weak.
- Threshold does not solve high-confidence semantic misretrieval.
- Answer quality evaluation is diagnostic, not comprehensive.
- No load testing, auth, async ingestion worker, production retry/backoff, reranking, MMR, hybrid search, or Kubernetes deployment yet.

## 17. Final Assessment

There is no blocking technical issue for portfolio submission after the failure-handling hardening in this audit. The project is strong as a backend/RAG evaluation portfolio because it shows controlled configuration selection, held-out validation, honest limitations, source-aware API behavior, Dockerization, ingestion, answer diagnostics, and monitoring.

The main story should be framed as engineering rigor and evaluation discipline, not as achieving high general-purpose RAG accuracy. The strongest interview point is the discovered trade-off: single-document coverage is good, but multi-document completeness remains difficult, and duplicate chunks plus semantic confusion require future retrieval-diversity or reranking work.
