# Answer Evaluation Human Review Guide

## Scope

This guide supports manual verification of the Answer Quality Evaluation diagnostic results. It does not start Phase 18 Monitoring. It does not change retrieval, generation, threshold, prompt, judge scores, or README content.

Review target:

- 11 generated answers in `results/answer_evaluation/answer_eval_human_review.csv`
- 3 fallback rows are excluded from detailed answer review because they were already deterministically verified as expected fallback with LLM generation skipped.

Human review fields must be filled by the reviewer, not by Codex.

## Recommended Review Order

For each row, review in this order:

1. Question
2. Reference summary and rubric fields
3. Generated answer
4. Expected, returned, and retrieved sources
5. Retrieved evidence excerpts
6. Human score fields
7. Judge result, for comparison only

The markdown packet `results/answer_evaluation/human_review_packet.md` follows this order so the reviewer can make a first-pass judgement before checking the judge.

## Correctness Rubric

Correctness asks whether the answer itself is factually right for the question.

| Score | Label | Criteria |
|---:|---|---|
| 2 | Correct | Core answer is factually correct and contains no important wrong claim. |
| 1 | Partially Correct | Core direction is right, but there are omissions, inaccuracies, or ambiguity that make the answer insufficient to trust as-is. |
| 0 | Incorrect | Core answer is wrong, the question is misread, or an important wrong claim is present. |

Judge score should not drive the human score. Use `reference_answer_summary`, `required_points`, `allowed_variations`, and `disallowed_claims`.

## Completeness Rubric

Completeness asks whether the answer covers the required troubleshooting points.

| Score | Label | Criteria |
|---:|---|---|
| 2 | Sufficiently Complete | Covers the core of the required points. |
| 1 | Partially Complete | Covers some required points but misses at least one important point. |
| 0 | Major Missing Content | Does not cover the core requirement of the question. |

For multi-document questions, check whether the answer includes the key point needed from each expected source.

## Faithfulness Rubric

Faithfulness asks whether factual claims in the generated answer are supported by the supplied retrieved context.

| Score | Label | Criteria |
|---:|---|---|
| 2 | Grounded | Factual claims are sufficiently supported by retrieved context and no material unsupported claim is present. |
| 1 | Mostly Grounded | Most claims are supported, but minor unsupported or unclear claims exist. |
| 0 | Materially Unsupported / Contradicted | Important factual claims are unsupported by retrieved context or contradict it. |

A statement can be true in the real world but still unsupported for faithfulness if the supplied retrieved context does not support it.

## Source Support Rubric

Source Support asks whether returned sources support the core generated answer.

| Score | Label | Criteria |
|---:|---|---|
| 2 | Sources support core answer | Returned sources support the main answer. |
| 1 | Partial support | Returned sources support only part of the main answer. |
| 0 | No core support | Returned sources do not support the main answer. |

Do not confuse Source Support with Source Presence. Source Presence checks expected `doc_id` matches. Source Support checks whether the answer is actually backed by the returned evidence.

## Failure Type Rubric

Use one of these values for `human_final_failure_type`:

| Value | Definition |
|---|---|
| `no_material_failure` | No material answer-quality failure. Retrieval differences may exist but did not materially harm the answer. |
| `retrieval_failure` | Necessary evidence was not retrieved, limiting answer quality. |
| `generation_failure` | Necessary evidence was available in context, but the answer still omitted, misstated, or mishandled it. |
| `combined_failure` | Retrieval was incomplete and generation added unsupported, contradicted, or misleading content. |

## High Priority Review Cases

Review these first:

- `ans_eval_007` / `eval_027`
- `ans_eval_009` / `eval_043`
- `ans_eval_010` / `eval_045`
- `ans_eval_011` / `eval_046`

Also prioritize any row with judge score below 2, low judge confidence, unsupported claims, contradicted claims, or multi-document type.

## eval_027 Diagnostic Guide

This is the ConfigMap / Secrets confusion case. Check:

- Is the question ConfigMap-centered?
- Are returned sources Secret-centered?
- Does the generated answer over-center Secret-specific content?
- Are required ConfigMap points missing?
- Is the answer faithful to retrieved context even if it is not correct for the original question?
- Does this show correctness and faithfulness separating?

This case can demonstrate that a model may faithfully answer from the wrong context while still failing correctness.

## eval_043 Diagnostic Guide

This is a ConfigMap + Secret multi-document case. Check:

- Is the ConfigMap source missing?
- Did the answer infer ConfigMap behavior without retrieved evidence?
- Is the unsupported ConfigMap claim material to the answer?
- Did source incompleteness cause answer incompleteness?
- Is `combined_failure` appropriate?

## eval_045 Diagnostic Guide

This case tests expected source presence versus actual answer support. Check:

- One expected source is missing; did that absence materially harm the answer?
- Did an alternative Auto Scaling troubleshooting source provide enough support?
- Is `no_material_failure` appropriate despite expected doc absence?
- Does this show that expected source presence is not identical to actual source support?

## eval_046 Diagnostic Guide

This is an RDS + VPC Reachability Analyzer multi-document case. Check:

- Is the Reachability Analyzer source missing?
- Did the answer narrow to RDS-only troubleshooting?
- Are unsupported claims present?
- Are contradicted claims present?
- Did retrieval incompleteness lead to answer failure?

## Judge-Human Agreement Policy

LLM Judge result is not final ground truth. After human review:

- If judge and human agree, use the result as confirmed diagnostic evidence.
- If they disagree, human judgement is preferred for final diagnostic interpretation.
- Disagreements should be kept as useful evidence about judge limitations.

Agreement can be calculated after all human fields are filled:

- exact agreement per metric
- within-1 agreement per metric
- disagreement cases
- final human failure distribution

Do not calculate agreement while human fields are blank.

## Required Human Fields

Fill these columns in `results/answer_evaluation/answer_eval_human_review.csv`:

- `human_correctness`
- `human_completeness`
- `human_faithfulness`
- `human_source_support`
- `human_agrees_with_judge`
- `human_final_failure_type`
- `human_notes`

Allowed scores for the four score fields: `0`, `1`, `2`.

Allowed final failure types:

- `no_material_failure`
- `retrieval_failure`
- `generation_failure`
- `combined_failure`

## Completion Rule

Human review is complete only when all 11 generated-answer rows have all required human score fields, `human_agrees_with_judge`, and `human_final_failure_type` filled.

Until then, reports should say: Human review incomplete.
