# Portfolio Summary

이 문서는 이 프로젝트를 이력서, 자기소개서, 기술면접에서 설명하기 위한 요약입니다. 모든 수치는 `docs/FINAL_TECHNICAL_AUDIT.md`와 기존 raw result를 기준으로 작성했습니다.

## 1. Recommended Positioning

추천 포지셔닝:

> Evaluation-driven CloudOps RAG for AWS and Kubernetes troubleshooting.

보조 메시지:

- Retrieval부터 answer quality까지 분리해 평가한 RAG 프로젝트.
- AWS/Kubernetes 공식 문서를 대상으로 failure-driven improvement를 수행한 CloudOps RAG.
- 단순 챗봇 구현이 아니라 검색 품질, fallback, 답변 품질, 운영 관측성을 함께 검증한 프로젝트.

## 2. Resume Bullets

- AWS/Kubernetes 공식 troubleshooting 문서 20개를 대상으로 CloudOps RAG를 구축하고, 50문항 retrieval evaluation을 설계해 chunking, embedding, Top-k, threshold를 순차 비교했습니다. Frozen configuration은 held-out in-scope 8문항에서 expected document Top-3 retrieval 8/8, MRR 0.9375를 기록했습니다.

- Retrieval과 generation 평가를 분리해 14문항 answer-quality diagnostic을 수행하고, 11개 generated answer를 correctness, completeness, faithfulness, source support 기준으로 human verification했습니다. LLM-as-a-Judge와 human score는 44개 score assignment 중 39개 exact match, 44개 within-one match를 보였습니다.

- Multi-document retrieval failure를 분석해 관련 문서 하나는 찾지만 모든 required evidence를 함께 회수하지 못하는 문제를 확인했습니다. Duplicate chunk occupancy 가설을 세우고 Dev-set cap=2 후처리 실험을 수행해 Multi All-Hit@5가 2/6에서 4/6으로 변하는 promising direction을 확인했지만, 새 held-out 검증 전에는 frozen configuration에 반영하지 않았습니다.

## 3. Self-Introduction Version, About 300 Korean Characters

AWS와 Kubernetes 공식 troubleshooting 문서를 대상으로 CloudOps RAG를 구축했습니다. 단순히 문서를 벡터 DB에 넣고 답변을 생성하는 데서 끝내지 않고, 50문항 retrieval evaluation을 만들어 chunking, embedding, Top-k, threshold를 비교하고 frozen configuration을 held-out set에서 검증했습니다. 이후 answer quality와 multi-document failure를 분석해, RAG 성능을 기능이 아니라 측정 가능한 engineering problem으로 다뤘습니다.

## 4. Self-Introduction Version, About 500 Korean Characters

Cloud/AWS/Kubernetes troubleshooting에서는 자연스러운 답변보다 공식 근거를 정확히 찾는 능력이 중요하다고 보고 CloudOps RAG를 만들었습니다. 20개 공식 문서를 corpus로 구성하고 50문항 retrieval evaluation을 설계해 chunking, embedding, Top-k, threshold를 순차적으로 비교했습니다. Frozen configuration은 held-out in-scope 8문항에서 expected document Top-3 retrieval 8/8을 기록했지만, multi-document All-Hit은 held-out 0/3으로 약하다는 점도 확인했습니다. 이후 14문항 answer diagnostic과 human verification을 통해 faithfulness와 correctness가 다를 수 있음을 분석했고, duplicate chunk occupancy 개선 가설을 Dev-set cap=2 실험으로 검증했습니다. 최종적으로 FastAPI, Docker, runtime ingestion, Prometheus metrics까지 붙여 서비스 관점으로 정리했습니다.

## 5. Interview Answer: "이 프로젝트가 뭔가요?" 30 Seconds

AWS와 Kubernetes 공식 troubleshooting 문서를 기반으로 만든 evaluation-driven RAG 프로젝트입니다. FastAPI로 질문을 받고, OpenAI embedding과 Chroma retrieval을 거쳐 threshold를 통과하면 gpt-4o-mini가 source와 함께 답변합니다. 핵심은 단순 구현이 아니라 retrieval evaluation, held-out validation, answer-quality diagnostic, failure analysis를 분리해서 수행했다는 점입니다. 특히 single-document retrieval은 잘 동작했지만 multi-document completeness가 약하다는 한계를 수치로 확인했습니다.

## 6. Interview Answer: "이 프로젝트가 뭔가요?" 1 Minute

이 프로젝트는 AWS/Kubernetes 운영 troubleshooting에서 공식 근거를 찾아 답변하는 CloudOps RAG입니다. 문제의식은 LLM이 그럴듯하게 말하는 것보다, 관련 운영 문서를 실제로 찾아오고 근거가 부족하면 답변을 거부하는 흐름이 더 중요하다는 것이었습니다. 그래서 20개 공식 문서와 50문항 retrieval evaluation을 만들고, chunking, embedding, Top-k, threshold를 비교한 뒤 frozen configuration을 held-out set에서 검증했습니다. 이후 14문항 answer-quality diagnostic을 통해 답변의 correctness, completeness, faithfulness, source support를 확인했습니다. 가장 중요한 발견은 multi-document 질문에서 하나의 관련 문서는 잘 찾지만 모든 evidence를 함께 가져오는 데 약하다는 점이었고, duplicate chunk occupancy 가설을 cap=2 Dev-set 실험으로 검증했습니다. 마지막으로 FastAPI, runtime ingestion, Docker, Prometheus metrics까지 붙여 서비스 형태로 정리했습니다.

## 7. Interview Answer: "왜 이 프로젝트를 했나요?"

클라우드와 인프라 운영에서는 답변이 자연스러운지보다 어떤 공식 문서에 근거했는지가 더 중요하다고 생각했습니다. 특히 troubleshooting 상황에서는 관련 문서를 잘못 찾으면 답변이 그럴듯해도 실제 조치가 틀릴 수 있습니다. 그래서 RAG를 단순히 구현하는 대신, retrieval quality와 fallback, answer quality, failure 원인을 직접 측정하는 프로젝트로 설계했습니다. 이전에 로그나 지표를 통해 문제를 분석하듯이, RAG도 결과를 관찰하고 실패를 분해해야 실제 서비스에 가까워진다고 봤습니다.

## 8. Interview Answer: "가장 어려웠던 점은 무엇인가요?"

가장 어려웠던 점은 multi-document retrieval이었습니다. single-document 질문은 비교적 잘 맞았지만, 두 개 이상의 문서가 필요한 질문에서는 관련 문서 하나만 찾고 나머지를 놓치는 경우가 반복됐습니다. 분석해보니 Top-k 안에 같은 문서의 duplicate chunk가 많이 들어와 다른 evidence document를 밀어내는 현상이 있었고, 이를 검증하기 위해 Dev-set에서 per-document cap=2 후처리 실험을 했습니다. 그 결과 Multi All-Hit@5가 2/6에서 4/6으로 좋아지는 방향을 확인했지만, post-hoc Dev 실험이기 때문에 production frozen config에는 넣지 않았습니다.

## 9. Interview Answer: "성능이 좋은가요?"

잘 되는 부분과 약한 부분을 분리해서 봐야 합니다. Held-out in-scope 8문항에서는 expected document가 Top-3 안에 8/8로 들어왔고, single-document 질문도 5/5가 모든 cutoff에서 성공했습니다. 하지만 multi-document 질문은 Held-out All-Hit@5가 0/3이라 필요한 모든 evidence를 함께 가져오는 데 약했습니다. Answer evaluation에서도 retrieval coverage와 answer correctness가 자동으로 같이 가지는 않았고, Human Review에서는 retrieval 실패뿐 아니라 근거가 있어도 핵심 포인트를 충분히 사용하지 못한 generation-side failure도 관찰됐습니다. 그래서 이 프로젝트는 높은 점수만 주장하기보다 어디가 강하고 어디가 약한지 측정한 프로젝트라고 설명하는 것이 맞습니다.

## 10. Interview Answer: "Hallucination은 어떻게 막았나요?"

완전히 막았다고 말하지는 않습니다. 이 프로젝트에서는 Top-1 Chroma L2 distance threshold를 두고, 기준보다 거리가 크면 fallback을 반환하면서 LLM 호출을 건너뛰도록 했습니다. 또한 답변에는 source를 반환하고, answer evaluation에서 faithfulness와 source support를 따로 확인했습니다. 다만 threshold는 low-confidence OOS query를 거르는 장치이지, high-confidence semantic misretrieval까지 막지는 못합니다. 예를 들어 ConfigMap 질문에 Secrets context가 검색되면 threshold를 통과해도 답변이 틀릴 수 있습니다.

## 11. Interview Answer: "왜 cap=2를 production에 적용하지 않았나요?"

cap=2는 duplicate chunk occupancy 문제를 줄이는 promising Dev-set experiment였습니다. Dev Multi All-Hit@5가 2/6에서 4/6으로 변했고 average unique docs도 늘었지만, 이 실험은 held-out 평가 이후 수행한 post-hoc 분석이었습니다. 새로운 untouched validation set에서 검증하지 않았기 때문에 frozen configuration에 반영하지 않았습니다. 성능이 좋아 보이는 아이디어라도 검증 절차를 지키지 않으면 과적합 위험이 있다고 판단했습니다.

## 12. Technical Interview Questions

1. 왜 Chroma를 선택했나요?
   - 개인 프로젝트와 실험 반복에 적합한 local persistent vector DB이기 때문입니다. 운영형 분산 vector DB보다 설정 비용이 낮고, corpus가 20문서 규모라 충분했습니다. 다만 대규모 운영, 고가용성, 분산 검색 관점에서는 Qdrant 같은 대안이 더 적합할 수 있습니다.

2. 왜 OpenAI `text-embedding-3-small`을 선택했나요?
   - Dev-set에서 MiniLM보다 Hit@3이 높았습니다. OpenAI는 외부 API 비용과 latency, key dependency가 있지만, 이 프로젝트에서는 retrieval quality를 우선했습니다. MiniLM은 local/offline 실행이 중요할 때 좋은 대안입니다.

3. 왜 character-based chunking을 사용했나요?
   - 초기 실험에서 구현과 재현이 단순하고 chunk boundary 비교가 쉬웠기 때문입니다. 대신 token-aware, section-aware, semantic chunking보다 문서 구조를 덜 활용한다는 한계가 있습니다. 이 한계는 README와 limitations에 명시했습니다.

4. 왜 `1024/128`을 선택했나요?
   - Development set에서 baseline `512/0`보다 Top-3 coverage가 32/36에서 33/36으로 증가했습니다. 반대로 Hit@1과 MRR은 내려갔기 때문에 across-the-board improvement가 아니라 coverage-ranking trade-off입니다.

5. 왜 `top_k=5`인가요?
   - k=3과 overall Hit은 같았지만, k=5에서 Dev Multi All-Hit이 0/6에서 2/6으로 올라갔습니다. CloudOps 질문은 여러 문서 evidence가 필요한 경우가 있어 k=5를 선택했습니다. 대신 context가 길어지고 duplicate chunks가 늘어나는 비용이 있습니다.

6. L2 threshold는 무엇을 의미하나요?
   - Chroma가 반환한 L2 distance에서 값이 낮을수록 query와 retrieved chunk가 더 유사하다는 의미입니다. 이 프로젝트는 Top-1 distance가 `1.042478` 이하이면 accept, 초과하면 fallback으로 처리합니다. threshold는 corpus와 sample에 의존합니다.

7. Hit@k와 MRR의 차이는 무엇인가요?
   - Hit@k는 expected document가 cutoff 안에 있는지를 보는 coverage metric입니다. MRR은 expected document가 얼마나 높은 순위에 있는지를 보는 ranking metric입니다. 그래서 Hit@3은 같아도 rank 1인지 rank 3인지에 따라 MRR은 달라질 수 있습니다.

8. Multi Any-Hit과 Multi All-Hit은 왜 나눴나요?
   - Multi-document 질문에서는 관련 문서 하나만 찾는 것과 필요한 모든 evidence를 찾는 것이 다릅니다. Any-Hit은 최소 하나를 찾았는지, All-Hit은 모든 expected document를 찾았는지 봅니다. 이 프로젝트의 핵심 약점은 Any-Hit은 높지만 All-Hit이 낮다는 점이었습니다.

9. 왜 threshold가 semantic misretrieval을 막지 못하나요?
   - threshold는 distance 기반 confidence gate입니다. 검색된 문서가 query와 가깝게 보이면 통과하지만, 그 가까운 문서가 실제 질문 의도와 다를 수 있습니다. ConfigMap 질문에 Secrets 문서가 high-confidence로 검색되는 경우가 대표적입니다.

10. cap=2의 trade-off는 무엇인가요?
    - 같은 문서 chunk가 Top-k를 점유하는 문제를 줄여 document diversity를 높일 수 있습니다. 하지만 single-document 질문에서 필요한 같은 문서 내 evidence를 충분히 가져오지 못할 위험이 있습니다. 또한 이 프로젝트에서는 Dev-only post-hoc candidate라 production에는 적용하지 않았습니다.

11. evaluation collection과 runtime collection을 왜 분리했나요?
    - 평가 결과는 frozen corpus와 frozen collection에 묶여 있어야 재현 가능합니다. 반면 runtime ingestion은 사용자가 새 URL을 넣으며 계속 변할 수 있습니다. 두 collection을 분리하면 평가 재현성과 서비스 확장성을 동시에 유지할 수 있습니다.

12. 왜 synchronous ingestion을 선택했나요?
    - 현재 문서 규모와 포트폴리오 목적에서는 흐름이 단순하고 관찰 가능하기 때문입니다. fetch, parse, chunk, embed, index 상태를 한 request 안에서 추적할 수 있습니다. 대용량 문서나 동시 ingestion이 많아지면 background worker가 필요합니다.

13. retry/backoff는 어떻게 설계했나요?
    - OpenAI embedding/generation 호출에만 bounded application-level retry를 적용했습니다. SDK retry는 `max_retries=0`으로 비활성화해 중첩 retry를 막고, 한 logical operation은 최대 3회만 시도합니다. 429, connection failure, selected 5xx만 재시도하며 timeout과 permanent 4xx는 재시도하지 않습니다.

14. Prometheus label cardinality는 어떻게 관리했나요?
    - `/metrics` label에는 question text, answer text, URL, doc_id, chunk_id, raw exception message 같은 high-cardinality 값을 넣지 않았습니다. 대신 route, method, status code, operation, bounded failure reason처럼 제한된 label만 사용했습니다. 이는 metric storage 폭증과 민감 정보 노출을 줄이기 위한 설계입니다.

15. 왜 answer evaluation과 retrieval evaluation을 분리했나요?
    - retrieval은 expected evidence를 찾았는지를 평가하고, answer evaluation은 그 evidence로 좋은 답을 만들었는지를 평가합니다. expected document를 찾았어도 답변이 불완전할 수 있고, exact expected doc이 없어도 다른 source가 답변을 support할 수 있습니다. 그래서 두 layer를 분리해야 실패 원인을 더 정확히 볼 수 있습니다.

## 13. Role-Specific Emphasis

Infra / Cloud / DevOps:

- AWS/Kubernetes troubleshooting domain, source-grounded answer flow, fallback behavior.
- Docker runtime, bind-mount persistence, healthcheck, runtime ingestion lifecycle.
- Prometheus-compatible metrics and bounded-label policy.
- Timeout/failure handling and explicit limitations.

Backend:

- FastAPI API design, request/response contracts, error envelope consistency.
- Runtime ingestion, stable URL-based IDs, duplicate URL idempotency.
- Separation of route handlers, services, vector store, embedding, generation.
- Tests for API behavior, monitoring, ingestion failure, and OpenAI client failure normalization.

AI / RAG:

- Retrieval evaluation design using document-level ground truth.
- Hit@k, MRR, Multi Any-Hit, Multi All-Hit, threshold acceptance/rejection.
- Answer-quality diagnostic with human verification.
- Failure analysis for multi-document completeness and semantic confusion.

## 14. Caveats To Keep Visible

- Held-out Test has only 10 questions.
- Held-out in-scope has only 8 questions.
- Held-out OOS has only 2 questions.
- Answer diagnostic has only 11 generated answers.
- cap=2 is a Dev-only post-hoc candidate, not the frozen configuration.
- Threshold fallback does not solve semantic misretrieval.
- This is not a broad production benchmark.
