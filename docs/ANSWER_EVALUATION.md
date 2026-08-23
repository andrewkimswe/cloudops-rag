# Answer Quality Evaluation

## Evaluation Scope

This document records the Answer Quality Evaluation diagnostic workflow added after Phase 17 and before Phase 18 Monitoring. This work is not a new original project phase and does not start Phase 18.

The evaluation uses the existing frozen RAG generation snapshot. It does not regenerate answers, retune retrieval, change threshold, modify prompts, or update the README.

Frozen runtime snapshot:

```text
chunk_size = 1024
chunk_overlap = 128
chunk_unit = character
embedding_model = OpenAI text-embedding-3-small
vector_db = Chroma
retrieval_top_k = 5
top_1_l2_distance_threshold = 1.042478
generation_model = gpt-4o-mini
generation_temperature = 0
```

## Diagnostic Dataset

Dataset: `data/answer_evaluation/answer_eval_diagnostic.csv`

The diagnostic subset contains 14 questions selected from `data/evaluation/evaluation_full.csv`:

| Type | Count |
|---|---:|
| single-troubleshooting | 5 |
| discrimination | 3 |
| multi-document | 3 |
| out-of-scope | 3 |

The 11 generated-answer rows are evaluated by an LLM judge. The 3 fallback rows are excluded from answer-level judge scoring and are summarized through deterministic fallback checks.

## Deterministic Checks

Step 1 deterministic checks remain part of the evaluation record:

| Check | Result |
|---|---:|
| fallback correctness | 14/14 |
| answerable source any-hit | 10/11 |
| answerable source all-hit | 7/11 |
| multi-document source all-hit | 0/3 |

These checks evaluate structure and source presence. They do not evaluate whether the prose answer is correct, complete, or faithful.

## Judge Method

Judge model: `gpt-4.1-mini`

Reason for selection: the generation model is `gpt-4o-mini`, so `gpt-4.1-mini` gives a separate model family for diagnostic judging while staying lightweight enough for a small portfolio evaluation.

Judge configuration:

```text
answer-level judge calls = 11
claim-level judge calls = 5
temperature = 0
majority vote = not used
```

The judge receives the question, rubric summary, required points, allowed variations, disallowed claims, generated answer, returned source metadata, and retrieved context chunks. It is instructed to use only the supplied rubric and retrieved context, not outside knowledge.

Judge output is diagnostic evidence, not absolute ground truth. Human review fields are provided separately and remain pending.

## Judge Rubric

Scores use a compact 0-2 scale:

| Metric | 0 | 1 | 2 |
|---|---|---|---|
| Correctness | incorrect | partially correct | correct |
| Completeness | major required content missing | partially complete | sufficiently complete |
| Faithfulness | material unsupported or contradicted claims | mostly grounded with minor issues | sufficiently grounded |
| Source Support | sources do not support core answer | partial support | sources support core answer |

Fluency and style are not evaluated.

## Correctness

Distribution over 11 generated answers:

| Score | Count |
|---|---:|
| 2 | 7 |
| 1 | 3 |
| 0 | 1 |

Average score: 1.5455

This should not be reported as “answer accuracy.” The dataset is a 14-question diagnostic subset with only 11 generated answers.

## Completeness

Distribution over 11 generated answers:

| Score | Count |
|---|---:|
| 2 | 3 |
| 1 | 6 |
| 0 | 2 |

Average score: 1.0909

Completeness is the weakest answer-level metric in this run. Several answers are directionally correct but omit required troubleshooting points from the rubric.

## Faithfulness

Distribution over 11 generated answers:

| Score | Count |
|---|---:|
| 2 | 11 |
| 1 | 0 |
| 0 | 0 |

Average score: 2.0

This indicates that generated answers were generally grounded in the retrieved context. It does not mean the answers were always correct, because a model can faithfully answer from incomplete or wrong retrieved context.

## Source Support

Distribution over 11 generated answers:

| Score | Count |
|---|---:|
| 2 | 8 |
| 1 | 3 |
| 0 | 0 |

Average score: 1.7273

Source Support differs from Source Presence. Source Presence checks whether expected `doc_id` values are returned. Source Support checks whether the returned context actually supports the generated answer content.

## Claim-level Analysis

Claim-level analysis was limited to 5 selected candidates:

- `ans_eval_001` / `eval_001`
- `ans_eval_007` / `eval_027`
- `ans_eval_009` / `eval_043`
- `ans_eval_010` / `eval_045`
- `ans_eval_011` / `eval_046`

Claim support counts:

| Support status | Count |
|---|---:|
| supported | 24 |
| unsupported | 2 |
| contradicted | 1 |
| unclear | 4 |

Important findings:

- `eval_009` included an unsupported ConfigMap claim because the retrieved context did not include the expected ConfigMap source.
- `eval_011` included one unsupported and one contradicted claim around treating both required documents as RDS troubleshooting material.
- `eval_007` had unclear ConfigMap-related claims: the answer stayed close to the retrieved Secret context but failed to answer the ConfigMap question well.

## Retrieval vs Generation Failure

Final failure classification combines judge scores, deterministic missing expected sources, and claim-level unsupported or contradicted findings for candidate rows.

| Failure type | Count |
|---|---:|
| retrieval_failure | 1 |
| generation_failure | 5 |
| combined_failure | 2 |
| no_material_failure | 3 |

Definitions:

- `retrieval_failure`: required evidence source was missing and that explains the answer weakness.
- `generation_failure`: required evidence was present enough, but the answer was incomplete or incorrect.
- `combined_failure`: retrieval was incomplete and the generation also added unsupported or contradicted content.
- `no_material_failure`: no material issue found by this diagnostic judge run.

## Multi-document Cases

### eval_043 / ans_eval_009

Expected sources: `k8s_configmaps`, `k8s_secrets`

Returned sources: `k8s_secrets`

Missing source: `k8s_configmaps`

Required points: distinguish non-confidential configuration from sensitive credentials.

Observed answer behavior: the answer correctly used Secret context for sensitive credentials, but mentioned ConfigMaps without retrieved ConfigMap evidence.

Missing answer points: explicit ConfigMap non-confidential configuration support and a complete contrast between ordinary config and credentials.

Unsupported claims: ConfigMaps are typically used for ordinary runtime configuration, unsupported by the supplied retrieved context.

Final failure type: `combined_failure`

Interpretation: retrieval missed one required source, and the model partially filled the missing ConfigMap side from outside the retrieved context.

### eval_045 / ans_eval_010

Expected sources: `aws_alb_troubleshooting`, `aws_ec2_autoscaling_health_checks`

Returned sources: `aws_ec2_autoscaling_unhealthy_instances`, `aws_alb_troubleshooting`, `aws_alb_monitoring`

Missing source: `aws_ec2_autoscaling_health_checks`

Required points: combine ALB target health troubleshooting with Auto Scaling health check or replacement behavior.

Observed answer behavior: the answer used the returned Auto Scaling unhealthy-instances document plus ALB troubleshooting to cover the required operational idea.

Missing answer points: none flagged by the judge.

Unsupported claims: none flagged in claim-level analysis.

Final failure type: `no_material_failure`

Interpretation: deterministic expected-doc presence missed the exact expected Auto Scaling health-check doc, but a closely related returned Auto Scaling troubleshooting source was sufficient for this diagnostic answer.

### eval_046 / ans_eval_011

Expected sources: `aws_rds_troubleshooting`, `aws_vpc_reachability_analyzer`

Returned sources: `aws_rds_troubleshooting`, `aws_eks_auto_mode_troubleshooting`

Missing source: `aws_vpc_reachability_analyzer`

Required points: combine database connectivity checks with VPC path reachability analysis.

Observed answer behavior: the answer stayed mostly within RDS connectivity checks and did not retrieve or use the Reachability Analyzer document.

Missing answer points: Reachability Analyzer path analysis and explicit combination of DB checks with VPC path analysis.

Unsupported or contradicted claims: one unsupported claim around combining DB connectivity with VPC path analysis, and one contradicted claim that both relevant documents were RDS troubleshooting.

Final failure type: `combined_failure`

Interpretation: retrieval missed the VPC path-analysis source, and generation narrowed the answer to RDS material instead of preserving the multi-document requirement.

## ConfigMap / Secrets Case

Case: `eval_027` / `ans_eval_007`

Expected source: `k8s_configmaps`

Returned source: `k8s_secrets`

Final failure type: `retrieval_failure`

The generated answer was highly faithful to the returned Secret-centered context, but it failed the question’s expected ConfigMap-centered answer. This is the clearest diagnostic example of the difference between correctness and faithfulness:

- Correctness can be low when the answer does not address the intended question.
- Faithfulness can remain high when the answer stays grounded in the retrieved context.
- Wrong or incomplete retrieval can therefore produce a faithful but incorrect or incomplete answer.

No Secret-specific hallucination was flagged as unsupported, but the answer did not sufficiently state that ordinary non-sensitive configuration belongs in ConfigMaps while Secrets are reserved for sensitive values.

## Fallback Evaluation

The 3 out-of-scope rows were correct fallback cases and skipped LLM generation.

Fallback rows should be reported separately from generated-answer quality. Do not combine the 11 generated answer scores and 3 fallback correctness checks into a single overall accuracy number.

## Human Verification Workflow

Human review file: `results/answer_evaluation/answer_eval_human_review.csv`

Rows are marked for review when any of the following are true:

- judge confidence is low
- any answer-level metric score is below 2
- the question is multi-document
- unsupported claims are found
- deterministic retrieval indicated missing expected source or partial multi-document source coverage

Current pending human review count: 9

The human review fields are intentionally blank or `pending`. Codex did not mark human review as complete.

## Limitations

- The diagnostic subset is small: 14 questions, 11 generated answers.
- The judge was called once per answer; no majority vote was used.
- LLM judge output is not ground truth and should be human-reviewed.
- Claim-level analysis was limited to 5 selected candidates.
- Retrieved context snippets were used for judging; full official documents were not re-read by the judge.
- Failure classification combines deterministic and judge signals, so it should be treated as diagnostic rather than benchmark-grade labeling.

## Portfolio Interpretation

Good portfolio framing:

- The system separates retrieval coverage, fallback correctness, answer-level quality, source support, and claim-level faithfulness.
- The evaluation shows why high retrieval coverage is not enough: multi-document completeness and answer completeness still need separate checks.
- The ConfigMap/Secrets case demonstrates that correctness and faithfulness are different metrics.
- The multi-document cases demonstrate that source presence and source support are also different metrics.

Avoid saying:

- “Answer accuracy is X%.”
- “The RAG system is fully correct.”
- “The judge result is ground truth.”
