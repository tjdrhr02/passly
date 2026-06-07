# DA 포지션 면접 준비 — Passly 프로젝트 기반 Q&A

> 대상: DA(Data Architect) 포지션 면접
> 기준: Passly 프로젝트 실제 경험 및 설계 결정 근거
> 답변 분량: 질문당 약 200~250자 (1분 발화 기준)

---

## Q1. 이 프로젝트에서 DA로서 가장 중요하게 생각한 설계 원칙은 무엇인가요?

**A:**
설계 근거를 반드시 문서화하는 원칙을 가장 중요하게 생각했습니다. ERD 그림만으로는 DA 역량을 증명할 수 없기 때문입니다. 예를 들어 `exam_sessions.correct_count` 반정규화 결정은 단순히 컬럼을 추가한 것이 아니라, "시험 완료 후 correct_count는 변하지 않는다, 따라서 데이터 불일치 가능성이 없는 상태에서의 반정규화는 정당하다"는 근거를 `docs/02-erd-logical.md` 결정3에 명시했습니다. 마찬가지로 `document_versions` 분리, `chunk_embeddings` 1:1 분리 등 모든 결정에 배경, 선택, 근거, 트레이드오프를 함께 기록했습니다. 코드는 결과이고 문서는 의사결정 이력입니다. DA는 이 이력을 남기는 역할을 한다고 생각합니다.

---

## Q2. ERD 설계에서 가장 어려웠던 결정은 무엇이었나요?

**A:**
`document_versions`를 별도 테이블로 분리하는 결정이 가장 어려웠습니다. 가장 단순한 구조는 `learning_documents` → `document_chunks` 2단계이지만, 이렇게 하면 자격증 시험 가이드 개정 시 기존 청크를 즉시 삭제하게 됩니다. 이때 진행 중인 시험 세션이 청크 데이터를 참조하고 있으면 세션이 깨집니다. 그래서 `learning_documents` → `document_versions` → `document_chunks` 3단계 구조를 채택하고, 버전 전환 시 `is_active` 플래그만 교체하는 방식을 설계했습니다. 트레이드오프는 조회 쿼리에서 JOIN 깊이가 1단계 증가하는 것입니다. 이 결정을 `docs/02-erd-logical.md` 결정1에 기록했습니다.

---

## Q3. 벡터 DB를 도입한 이유와 설계 과정을 설명해주세요.

**A:**
Passly의 AI 질문 응답 기능은 RAG(Retrieval-Augmented Generation) 구조가 필요합니다. 사용자 질문과 의미적으로 유사한 PDF 청크를 찾아 LLM에 컨텍스트로 제공하는 방식입니다. 이를 위해 Gemini `text-embedding-004` 모델로 768차원 벡터를 생성하고 pgvector에 저장합니다. 설계 과정에서 두 가지를 결정했습니다. 첫째, 벡터가 768차원 x 4바이트 = 약 3KB/행이므로 비벡터 쿼리 성능 보호를 위해 `chunk_embeddings` 테이블을 `document_chunks`와 1:1 분리했습니다. 둘째, 3만 청크 규모에서는 IVFFlat(lists=175, probes=15)이 적합하다고 판단했고, 전환 조건(10만 청크 초과 또는 recall@10 < 0.85)도 `docs/04-vector-schema.md`에 명시했습니다.

---

## Q4. RAG 파이프라인의 각 단계에서 어떤 데이터 설계 결정을 내렸나요?

**A:**
파이프라인은 5단계로 구성됩니다. Stage 1 업로드 단계에서는 `pipeline_runs` 테이블로 실행 이력을 추적하고, `document_versions`로 버전을 관리합니다. Stage 2 PDF 파싱 단계에서는 `source_type`(OFFICIAL_GUIDE/DUMP)에 따라 경로를 분기합니다. Stage 3 청킹 단계에서는 300~500 토큰 단위로 분할하고 섹션 경로 메타데이터를 보존합니다. Stage 4 임베딩 단계에서는 `model_name`과 `model_version`을 `chunk_embeddings`에 저장해 모델 교체 이력을 추적할 수 있도록 합니다. Stage 5 품질 평가 단계에서는 5개 지표(토큰 수, 텍스트 다양성, 구조 완결성, 인코딩 안정성, 섹션 경로 존재) 합산 점수가 60점 미만인 청크를 `is_active = false`로 처리해 검색에서 제외합니다.

---

## Q5. pgvector를 왜 OpenSearch 대신 선택했나요?

**A:**
ADR-001에서 세 가지 기준으로 결정했습니다. 첫째, 비용입니다. OpenSearch는 GCP에서 별도 클러스터가 필요하고 월 $50 이상이 드는 반면, pgvector는 이미 사용 중인 Cloud SQL에 확장으로 추가되어 추가 비용이 없습니다. 둘째, 운영 복잡도입니다. 소수(2~10명) 유저 규모에서 별도 검색 클러스터를 운영하는 것은 과잉 설계입니다. Cloud SQL 하나로 관계형 데이터와 벡터 검색을 통합 관리합니다. 셋째, DA 포트폴리오 관점에서 "RDBMS 안에서 Vector Index를 어떻게 설계했는가"를 더 깊이 설명할 수 있습니다. 트레이드오프로 ANN 검색 성능이 낮을 수 있지만, 수만 청크 규모에서는 차이가 미미합니다. 청크가 10만을 초과하면 HNSW 전환을 검토하는 조건도 명시했습니다.

---

## Q6. 데이터 품질은 어떻게 관리했나요?

**A:**
`docs/06-data-quality.md`에 세 가지 축으로 정의했습니다. 첫째, `quality_score` 정량화입니다. 토큰 수 적정성 30점, 텍스트 다양성 25점, 구조 완결성 20점, 인코딩 안정성 15점, 섹션 경로 존재 10점을 합산해 0~100점으로 평가합니다. 60점 미만은 검색에서 자동 제외됩니다. 둘째, 출처 추적입니다. `questions.source_chunk_id`로 AI 생성 문제가 어떤 청크 기반인지 추적하고, `chunk_embeddings.model_name`으로 임베딩 모델 교체 이력을 관리합니다. 셋째, `user_attempts` 불변 원칙입니다. 시험 결과는 사실이므로 API 레벨에서 DELETE 엔드포인트를 미제공하고, AGENTS.md 절대 금지 항목에도 명시했습니다. 이를 통해 오답 노트와 약점 분석의 신뢰성을 보장합니다.

---

## Q7. 클라우드 기반 DA와 온프레미스 DA의 차이는 무엇이라고 생각하나요?

**A:**
가장 큰 차이는 비용 구조와 확장성 결정 방식입니다. 온프레미스 DA는 하드웨어 용량을 선제적으로 확보해야 하지만, 클라우드 DA는 실제 사용량 기반으로 스케일링 정책을 설계합니다. 이 프로젝트에서는 Cloud Run의 0 인스턴스 스케일다운을 선택했는데(ADR-002), 이는 소수 유저가 하루 일정 시간만 사용하는 패턴을 분석한 결과입니다. 또한 로컬 개발과 GCP 배포의 코드 동일성을 `USE_VERTEX_AI` 환경변수 하나로 구현해(ADR-006), 개발-운영 환경 차이를 최소화했습니다. 클라우드 DA는 인프라 선택 근거를 ADR로 문서화하고, 서비스 성장에 따른 전환 조건을 미리 정의하는 것이 온프레미스 DA와 가장 다른 점이라고 생각합니다.

---

## Q8. 이 프로젝트에서 가장 어려웠던 설계 결정은 무엇이었나요?

**A:**
Hybrid Search의 RRF k=60 파라미터 결정이 가장 어려웠습니다. Vector Search만 사용할 경우 "LUIS", "AI-102" 같은 고유 기술 용어를 정확히 매칭하지 못하는 한계가 있었고, Full-text Search만 사용하면 의미 기반 유사도를 잡지 못합니다. 두 방식을 결합하기로 결정했으나, 점수 정규화 없이 순위만으로 통합하는 RRF 방식에서 k값이 1위 문서의 지배력에 직접 영향을 줍니다. k값을 낮추면 1위 문서가 과도하게 지배하고, 높이면 상위 순위의 의미가 희석됩니다. Cormack et al.(2009) 원 논문 기본값인 k=60을 적용하되, 이를 `docs/04-vector-schema.md`에 근거와 함께 명시했습니다. 실제 검색 품질 평가(docs/07-search-evaluation.md)에서 Hybrid Search가 Vector 단독 대비 recall@10이 개선됨을 확인해 결정을 검증했습니다.

---

## 핵심 키워드 요약 (면접 직전 복습용)

### ERD 설계
- document_versions 3단계: 버전 전환 시 진행 중 세션 보호, is_active 플래그 전환
- chunk_embeddings 1:1 분리: 3KB/행 벡터, 비벡터 쿼리 성능 보호, 모델 교체 시 독립 재생성
- correct_count 반정규화: 시험 완료 후 불변, 데이터 불일치 없는 반정규화 정당성
- user_attempts 불변: 시험 결과는 사실, DELETE 엔드포인트 미제공

### pgvector / 검색
- IVFFlat: lists=175 (ceil(sqrt(30000))), probes=15, 코사인 유사도
- 전환 조건: 10만 청크 초과 or P95 > 500ms or recall@10 < 0.85 → HNSW
- Hybrid Search: Vector(IVFFlat) + FTS(chunk_tsv GIN) + RRF(k=60)
- RRF k=60: Cormack et al.(2009) 기본값, 1위 과도 지배력 방지
- pgvector vs OpenSearch: Cloud SQL 통합, 비용 1/5, 운영 복잡도 최소화

### 데이터 품질
- quality_score 5개 지표: 토큰수 30 + 텍스트다양성 25 + 구조완결성 20 + 인코딩안정성 15 + 섹션경로 10
- 60점 미만: is_active = false, 검색 제외
- source_chunk_id: AI 생성 문제 출처 추적 (데이터 거버넌스)
- model_name / model_version: 임베딩 교체 이력 추적

### 클라우드 아키텍처
- Cloud Run: 0 인스턴스 스케일다운, 유휴 시간 비용 최소화
- USE_VERTEX_AI: false(로컬 Gemini API) / true(GCP Vertex AI), 코드 변경 없음
- ADR 문서화: 배경 - 비교 - 결정 - 근거 - 트레이드오프 형식

### 설계 원칙
- 문서 우선: 요구사항 → 개념 모델 → 논리 ERD → 물리 ERD → DDL → 코드
- 설계 근거 4요소: 배경 / 선택 / 근거 / 트레이드오프
- 반정규화 조건: 불변 데이터에 한해, 근거 명시 필수
- 불변 이력: 감사 추적 필요한 테이블은 DELETE 없이 설계
