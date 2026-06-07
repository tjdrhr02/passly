# Passly Architecture Decision Records (ADR)

> 이 문서는 Passly 프로젝트에서 내린 주요 기술 결정의 배경과 근거를 기록한다.
> "왜 이 기술을 골랐나요?" 질문에 이 문서로 답한다.

---

## ADR-001. PostgreSQL + pgvector vs OpenSearch

**결정일**: 2025-06
**상태**: 확정

### 배경
RAG 검색을 위해 Vector DB가 필요하다. 주요 후보는 OpenSearch, pgvector, Pinecone이었다.

### 비교

| 항목 | OpenSearch | pgvector | Pinecone |
|------|-----------|---------|---------|
| 인프라 | 별도 클러스터 필요 | PostgreSQL 확장 | 관리형 SaaS |
| GCP 비용 (월) | ~$50+ (최소 인스턴스) | Cloud SQL에 포함 | $70+ |
| 관계형 데이터 통합 | 별도 DB 필요 | 동일 DB에서 처리 | 별도 DB 필요 |
| Hybrid Search | BM25 + Vector 지원 | Full-text + Vector | Vector 위주 |
| DA 포트폴리오 가치 | OpenSearch 아키텍처 설명 | RDBMS 내 Vector 설계 설명 | 설계 깊이 낮음 |
| 운영 복잡도 | 높음 | 낮음 | 낮음 |

### 결정
**pgvector 선택**

### 근거
1. 소수 유저(2~10명) 규모에서 OpenSearch는 리소스 과잉. 월 비용이 pgvector 대비 5배 이상.
2. Cloud SQL 하나로 관계형 데이터와 Vector 검색을 통합 관리. 운영 복잡도 최소화.
3. DA 포트폴리오 관점에서 "PostgreSQL 안에서 Vector Index를 어떻게 설계했는가"를 더 깊이 설명 가능.
4. 사용자 증가 시 pgvector → OpenSearch 마이그레이션 경로가 명확하다.

### 트레이드오프
- OpenSearch 대비 ANN 검색 성능이 낮을 수 있다. 하지만 소규모 문서(수천 청크)에서는 차이 미미.
- Full-text search를 위해 `tsvector` 컬럼과 GIN 인덱스를 별도 구성해야 한다.

---

## ADR-002. Cloud Run vs Cloud Run + GKE

**결정일**: 2025-06
**상태**: 확정

### 배경
백엔드와 프론트엔드 컨테이너의 배포 환경을 결정해야 했다.

### 비교

| 항목 | Cloud Run | GKE |
|------|-----------|-----|
| 비용 (유휴 시) | 거의 $0 (0 인스턴스) | 최소 $70+/월 (노드 유지) |
| 운영 복잡도 | 낮음 (완전 관리형) | 높음 (노드/클러스터 관리) |
| 스케일링 | 자동 (요청 기반) | 수동 설정 필요 |
| 적합 규모 | 소규모~중규모 | 대규모 워크로드 |
| 배포 방법 | Docker 이미지 push | k8s manifest |

### 결정
**Cloud Run 선택**

### 근거
1. 소수 유저가 하루 일정 시간만 사용하는 패턴 → 유휴 시간이 길다. Cloud Run의 0 인스턴스 스케일다운으로 비용 최소화.
2. DA 포트폴리오 목적이므로 인프라 운영 복잡도보다 데이터 설계에 집중하는 것이 우선.
3. Cloud Run은 Docker Compose 환경에서 Cloud Run으로의 전환이 간단하다 (컨테이너 이미지 재사용).

### 트레이드오프
- Cold start 지연 (~1-3초). 첫 요청 시 딜레이 발생. 최소 인스턴스 1개로 완화 가능 (비용 약 $10/월 추가).
- 긴 처리 시간(PDF 파이프라인)은 Cloud Run 최대 60분 제한에 주의. 비동기 처리로 해결.

---

## ADR-003. FastAPI vs Spring Boot

**결정일**: 2025-06
**상태**: 확정

### 배경
백엔드 프레임워크 선택. 기존에 Spring Boot 경험이 있고 Python도 가능한 상황.

### 비교

| 항목 | FastAPI (Python) | Spring Boot (Java) |
|------|----------------|-------------------|
| AI 파이프라인 통합 | 자연스럼 (Python 생태계) | 별도 Python 서버 필요 |
| Vertex AI SDK | Python SDK 공식 지원 | Java SDK 제한적 |
| 비동기 처리 | async/await 기본 지원 | WebFlux 필요 |
| GCP 통합 | google-cloud 패키지 풍부 | 일부 제한 |
| 개발 속도 | 빠름 | 상대적으로 느림 |

### 결정
**FastAPI 선택**

### 근거
1. PDF 파싱, 청킹, 임베딩이 모두 Python 생태계 (PyMuPDF, LangChain, Vertex AI SDK).
2. Vertex AI Python SDK가 공식 지원되며 예제 코드가 풍부하다.
3. FastAPI의 Pydantic 스키마가 DA 포트폴리오의 데이터 모델 명세와 일치한다.

### 트레이드오프
- Spring Boot 대비 Java 진영의 엔터프라이즈 기능(Spring Security, JPA)이 부족. 프로덕션 규모에서는 재검토 필요.

---

## ADR-004. Gemini API vs OpenAI API

**결정일**: 2025-06
**상태**: 확정

### 배경
LLM과 Embedding 모델 선택.

### 비교

| 항목 | Gemini (Google) | OpenAI |
|------|----------------|--------|
| GCP 통합 | Vertex AI 네이티브 | 외부 API |
| 임베딩 모델 | text-embedding-004 (768d) | text-embedding-3-small (1536d) |
| 로컬 개발 | Gemini Developer API (무료 티어) | API 키 (유료) |
| 한국어 지원 | MMTEB 1위 | 양호 |
| 비용 | 무료 티어 포함 | 유료 |

### 결정
**Gemini API 선택 (Vertex AI)**

### 근거
1. GCP 네이티브 스택으로 통일. Cloud Run → Vertex AI 호출 시 서비스 계정으로 인증, API 키 불필요.
2. 로컬 개발에서는 Gemini Developer API (무료 티어)를 사용하고 GCP 배포 시 Vertex AI로 전환. 코드 동일.
3. Azure 자격증 도메인과 GCP 스택 조합이 "Cloud 환경 이해" 측면에서 포트폴리오 다양성 강점.

### 트레이드오프
- OpenAI 대비 한국어 RAG 품질 비교 검증 필요. 검색 품질 평가(docs/07-search-evaluation.md)에서 실측.

---

## ADR-005. PyMuPDF vs Document AI

**결정일**: 2025-06
**상태**: 확정

### 배경
덤프 PDF에서 문제/선택지/정답을 구조적으로 추출해야 한다.

### 비교

| 항목 | PyMuPDF | Document AI (GCP) |
|------|---------|-----------------|
| 비용 | 무료 (오픈소스) | 페이지당 과금 ($1.5/1000장) |
| 정확도 | 레이아웃 의존적 | 높음 (ML 기반) |
| 구현 복잡도 | 직접 파싱 로직 작성 | API 호출 |
| 오프라인 처리 | 가능 | 불가 |

### 결정
**PyMuPDF 우선 적용, Document AI는 보완재**

### 근거
1. 포트폴리오 목적의 소규모 데이터. 비용 부담 없이 시작 가능.
2. 덤프 PDF가 보통 일정한 형식을 가진다. 직접 파싱 로직 작성으로 충분히 처리 가능.
3. 파싱 실패 케이스 발생 시 Document AI로 보완하는 fallback 구조 설계.

### 트레이드오프
- 덤프 PDF 형식이 다양할 경우 파싱 로직 유지보수 비용 증가.
- 품질 문제: 파싱 품질이 앱 전체 품질을 결정한다. `pipeline_runs` 테이블에 파싱 실패율 기록 필수.

---

## ADR-006. 로컬 → GCP 전환 전략

**결정일**: 2025-06
**상태**: 확정

### 배경
개발 초기에는 로컬 Docker 환경에서 빠르게 개발하고, 완성 후 GCP로 배포해야 한다.

### 전환 전략

| 환경 | PostgreSQL | Embedding | LLM | 스토리지 |
|------|-----------|-----------|-----|---------|
| 로컬 | Docker pgvector/pgvector:pg17 | Gemini Developer API | Gemini Developer API | 로컬 파일시스템 |
| GCP | Cloud SQL (pgvector 확장) | Vertex AI Embeddings | Vertex AI Gemini | Cloud Storage |

### 환경변수 분기
```
USE_VERTEX_AI=false   → 로컬 (Gemini API 키 방식)
USE_VERTEX_AI=true    → GCP (서비스 계정 인증)
```

### 근거
- Gemini 모델명이 로컬/GCP 동일 (`text-embedding-004`, `gemini-2.0-flash`).
- 코드 변경 없이 환경변수만 전환.
- Cloud SQL의 pgvector 확장이 Docker의 pgvector와 동일하게 동작.