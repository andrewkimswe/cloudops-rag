# Answer Quality Judge Prompt Template

You are evaluating a generated CloudOps troubleshooting answer.

Use only the supplied reference rubric and retrieved context. Do not use outside knowledge.
Do not reward facts that are true in general unless they are supported by the supplied context or the reference rubric.
Evaluate content quality only; do not score fluency or writing style.

Inputs:

- question
- reference_answer_summary
- required_points
- allowed_variations
- disallowed_claims
- generated_answer
- returned source metadata
- retrieved context text

Return a single JSON object with:

```json
{
  "correctness_score": 0,
  "correctness_reason": "short reason",
  "completeness_score": 0,
  "missing_required_points": [],
  "faithfulness_score": 0,
  "unsupported_claims": [],
  "contradicted_claims": [],
  "source_support_score": 0,
  "source_support_reason": "short reason",
  "overall_failure_type": "retrieval_failure",
  "judge_confidence": "medium"
}
```

Allowed scores: 0, 1, 2.
Allowed `overall_failure_type`: `retrieval_failure`, `generation_failure`, `combined_failure`, `no_material_failure`.
Allowed `judge_confidence`: `low`, `medium`, `high`.
