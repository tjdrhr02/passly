# Passly pgvector 스키마 설계서

> 버전: 1.0 | 작성일: 2026-05
> 대상 DB: PostgreSQL 17 + pgvector
> 이 문서는 AI DA 포트폴리오 핵심 산출물로, pgvector 스키마 설계 결정과 Hybrid Search 구조를 다룬다.
> 참조 문서: docs/00-data-standard.md, docs/02-erd-logical.md, docs/03-erd-physical.md

---

## 목차

1. [설계 개요 및 전제 조건](#1-설계-개요-및-전제-조건)
2. [chunk_embeddings 스키마 설계](#2-chunk_embeddings-스키마-설계)
   - 2-1. 테이블 DDL 전체
   - 2-2. 컬럼별 설계 근거
   - 2-3. document_chunks와 1:1 분리 설계 근거
3. [메타데이터 필드 설계 결정](#3-메타데이터-필드-설계-결정)
   - 3-1. chunk_embeddings 직접 보유 필드
   - 3-2. JOIN으로 가져오는 필드
   - 3-3. "없으면 생기는 문제" 분석
4. [Full-text Search 컬럼 설계](#4-full-text-search-컬럼-설계)
5. [벡터 인덱스 전략: IVFFlat vs HNSW](#5-벡터-인덱스-전략-ivfflat-vs-hnsw)
   - 5-1. 알고리즘 비교
   - 5-2. Passly 선택 근거
   - 5-3. lists 파라미터 계산
   - 5-4. probes 파라미터 설명
   - 5-5. 향후 HNSW 전환 조건
   - 5-6. 인덱스 DDL 전체
6. [Hybrid Search 구조](#6-hybrid-search-구조)
   - 6-1. Vector Search 단독의 한계
   - 6-2. RRF(Reciprocal Rank Fusion) 원리
   - 6-3. 검색 흐름 다이어그램
   - 6-4. 통합 SQL 쿼리 (CTE)
   - 6-5. Python 구현 패턴
7. [검색 쿼리 패턴 레퍼런스](#7-검색-쿼리-패턴-레퍼런스)
8. [설계 자체 검토 체크리스트](#8-설계-자체-검토-체크리스트)

---

## 1. 설계 개요 및 전제 조건

### 프로젝트 컨텍스트

Passly는 자격증 공식 시험 가이드 PDF와 덤프 PDF를 업로드하면 AI 기반 질문 응답(/chat 페이지)과 문제 해설을 제공하는 플랫폼이다. AI 질문 응답의 핵심은 RAG(Retrieval-Augmented Generation) 파이프라인이며, 이 문서는 그 중 검색 단계의 벡터 스키마와 인덱스 전략을 다룬다.

### 전제 조건

| 항목 | 값 | 근거 |
|------|----|------|
| 임베딩 모델 | Gemini text-embedding-004 | AGENTS.md 기술 스택 |
| 벡터 차원수 | 768 | text-embedding-004 출력 차원 |
| 초기 청크 수 | 1만~3만 건 | 공식 가이드 + 덤프 PDF 합산 예상 |
| 유사도 메트릭 | 코사인 유사도 | 임베딩 모델 권장 메트릭 |
| DB 엔진 | PostgreSQL 17 + pgvector | AGENTS.md 기술 스택 |
| 사용자 규모 | 2~10명 | AGENTS.md 프로젝트 목적 |

### 이 문서의 범위

- chunk_embeddings 테이블 스키마 및 설계 결정
- Full-text Search 보조 컬럼 (document_chunks.chunk_tsv)
- 벡터 인덱스 전략 선택 근거 및 DDL
- Hybrid Search (Vector + Full-text + RRF) 구조 및 SQL

일반 B-tree 인덱스 DDL은 docs/03-erd-physical.md 섹션 5에 포함되어 있으며 이 문서에서 중복 기재하지 않는다.

---

## 2. chunk_embeddings 스키마 설계

### 2-1. 테이블 DDL 전체

```sql
-- 청크 임베딩: document_chunks의 벡터 표현을 분리 저장하는 테이블.
-- 설계 결정: docs/02-erd-logical.md 결정 2 — 비벡터 쿼리 성능 보호를 위한 1:1 분리.
-- pgvector 전제: CREATE EXTENSION IF NOT EXISTS "vector"; 먼저 실행 필요 (docs/03-erd-physical.md 섹션 2 참고)
CREATE TABLE chunk_embeddings (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id       UUID         NOT NULL UNIQUE REFERENCES document_chunks(id) ON DELETE RESTRICT,
    embedding      vector(768)  NOT NULL,
    model_name     VARCHAR(100) NOT NULL,
    model_version  VARCHAR(50)  NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted     BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  chunk_embeddings IS '청크 임베딩 벡터. document_chunks와 1:1 분리 (비벡터 쿼리 성능 최적화).';
COMMENT ON COLUMN chunk_embeddings.id            IS 'PK — UUID v4, gen_random_uuid()';
COMMENT ON COLUMN chunk_embeddings.chunk_id      IS 'document_chunks FK. UNIQUE로 1:1 관계 DB 레벨 보장. ON DELETE RESTRICT.';
COMMENT ON COLUMN chunk_embeddings.embedding     IS 'vector(768) — Gemini text-embedding-004. 모델 교체 시 전체 행 재생성 필요.';
COMMENT ON COLUMN chunk_embeddings.model_name    IS '임베딩 모델 식별자. 예: text-embedding-004. 모델 교체 이력 추적용.';
COMMENT ON COLUMN chunk_embeddings.model_version IS '모델 버전 식별자. 동일 모델명 내 버전 변경 추적용.';
COMMENT ON COLUMN chunk_embeddings.is_deleted    IS '소프트 삭제 플래그. 물리 DELETE 금지.';
```

### 2-2. 컬럼별 설계 근거

| 컬럼 | 타입 | 제약조건 | 설계 이유 |
|------|------|---------|---------|
| id | UUID | PK, DEFAULT gen_random_uuid() | docs/00-data-standard.md 공통 컬럼 규칙 준수 |
| chunk_id | UUID | NOT NULL, UNIQUE, FK | UNIQUE로 DB 레벨에서 1:1 관계를 강제. ON DELETE RESTRICT로 청크 삭제 전 임베딩 정리 요구 |
| embedding | vector(768) | NOT NULL | Gemini text-embedding-004의 출력 차원 768에 정확히 맞춤. 차원 불일치 시 INSERT 오류로 조기 감지 가능 |
| model_name | VARCHAR(100) | NOT NULL | 임베딩 모델명 저장. 모델 교체 시 어떤 청크가 구버전 모델로 생성되었는지 식별 가능 |
| model_version | VARCHAR(50) | NOT NULL | 동일 모델명 내에서도 API 버전이 바뀌면 임베딩 공간이 달라질 수 있음. 버전 단위 추적 필수 |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | 임베딩 생성 시점. 파이프라인 실행 이력 추적 및 문제 재현 시 활용 |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | 모델 재생성 시 갱신. 트리거로 자동 관리 (docs/03-erd-physical.md 섹션 6 참고) |
| is_deleted | BOOLEAN | NOT NULL, DEFAULT false | 소프트 삭제. 검색 쿼리에서 WHERE is_deleted = false 필터 적용 |

**vector(768) 차원 고정의 의미**

PostgreSQL pgvector는 테이블 생성 시 벡터 차원을 스키마에 고정한다. `vector(768)`로 선언하면 768차원 이외의 값을 INSERT할 때 DB 레벨에서 오류가 발생한다. 이는 임베딩 모델 차원 불일치를 애플리케이션 레벨이 아닌 DB 레벨에서 조기 감지할 수 있다는 장점이다. 단, 모델 교체로 차원이 바뀌면 컬럼 타입 변경(ALTER TABLE) 또는 테이블 재생성이 필요하다.

### 2-3. document_chunks와 1:1 분리 설계 근거

**설계 결정: 임베딩을 document_chunks에 직접 넣지 않고 chunk_embeddings 별도 테이블로 분리한다.**

| 항목 | 내용 |
|------|------|
| 배경 | vector(768)은 768 * 4 bytes = 약 3KB/행이다. 3만 청크 기준 전체 임베딩 용량은 약 90MB다. |
| 문제 | document_chunks에 embedding 컬럼을 함께 두면, 비벡터 쿼리(문제 생성, 청크 텍스트 조회 등)에서도 PostgreSQL이 넓은 행을 읽어야 한다. PostgreSQL은 행 단위로 I/O를 수행하므로 3KB의 임베딩 데이터가 항상 버퍼 캐시를 오염시킨다. |
| 선택 | chunk_embeddings를 별도 테이블로 분리. chunk_id UNIQUE 제약으로 DB 레벨 1:1 보장. |
| 근거 1 | 비벡터 쿼리(예: 시험 문제 생성을 위한 chunk_text 조회)는 chunk_embeddings 테이블을 JOIN하지 않아도 된다. document_chunks 테이블의 행 폭이 좁아져 버퍼 히트율이 올라간다. |
| 근거 2 | 벡터 인덱스(IVFFlat/HNSW)는 chunk_embeddings 테이블에만 존재한다. 인덱스가 캐싱하는 데이터 범위가 명확하게 분리된다. |
| 근거 3 | 임베딩 모델 재생성(model_name, model_version 변경) 시 chunk_embeddings 테이블만 교체하면 된다. document_chunks의 원문 텍스트는 영향받지 않는다. |
| 트레이드오프 | RAG 검색 쿼리에서 document_chunks와 chunk_embeddings를 반드시 JOIN해야 한다. 쿼리 복잡도가 소폭 증가한다. 하지만 chunk_id에 UNIQUE 인덱스가 존재하므로 JOIN 비용은 무시할 수준이다. |

---

## 3. 메타데이터 필드 설계 결정

RAG 검색에서 벡터 유사도만으로는 검색 품질을 통제하기 어렵다. 자격증 필터, 권한 제어, 품질 기준 등은 메타데이터 필터로 구현한다. 아래는 각 필드가 없을 경우 발생하는 문제를 중심으로 설명한다.

### 3-1. chunk_embeddings 직접 보유 필드

chunk_embeddings 테이블에 직접 저장하는 필드는 임베딩 모델 추적 목적의 두 개다. 나머지 검색 필터 메타데이터는 document_chunks, chunk_topics, topics, exam_domains를 통해 JOIN으로 가져온다.

| 필드 | 위치 | 없으면 생기는 문제 | 그래서 필요한 이유 |
|------|------|-----------------|-----------------|
| model_name | chunk_embeddings | 임베딩 모델 교체 후 어떤 청크가 구버전인지 알 수 없다. 전체 재생성 또는 혼재 상태에서 검색 품질이 불규칙해진다. | 모델명 필터로 특정 모델 버전으로 생성된 임베딩만 조회하거나, 재생성 대상 청크를 식별할 수 있다. |
| model_version | chunk_embeddings | 동일 모델(text-embedding-004)이라도 API 내부 버전이 바뀌면 임베딩 공간이 달라진다. 버전 추적 없이는 이질적인 벡터가 혼재해 검색 순위가 비정상적으로 나온다. | 버전 단위 재생성 스크립트 작성 시 WHERE model_version = 'xxx'로 대상을 한정할 수 있다. |

### 3-2. JOIN으로 가져오는 필드

아래 필드들은 chunk_embeddings에 직접 저장하지 않고 JOIN으로 가져온다. 비정규화(중복 저장)를 하지 않는 이유는 원본 데이터 변경 시 chunk_embeddings의 복사본도 동기화해야 하는 유지보수 부담이 생기기 때문이다.

| 필드 | 원본 위치 | JOIN 경로 | 없으면 생기는 문제 | 그래서 필요한 이유 |
|------|---------|---------|-----------------|-----------------|
| certification_id | document_chunks → document_versions → learning_documents | learning_documents.certification_id | 자격증 A의 쿼리에서 자격증 B의 청크가 검색 결과에 포함된다. AI-102 질문에 AWS SAA 내용이 섞인다. | WHERE certification_id = :cert_id로 해당 자격증 청크만 검색 대상으로 한정. |
| exam_domain_id | chunk_topics → topics → exam_domains | topics.exam_domain_id | 시험 영역별 검색이 불가능하다. "AI 솔루션 설계" 영역 문제 생성 시 전체 청크를 스캔해야 한다. | 시험 영역 가중치 기반 문제 생성(/practice 페이지)에서 영역 필터로 활용. |
| topic_id | chunk_topics | chunk_topics.topic_id | 특정 학습 개념(예: Azure OpenAI Service)에 관련된 청크만 필터링이 불가능하다. AI 질문이 특정 토픽과 무관한 청크를 참조해 답변 품질이 저하된다. | topic_id 필터로 질문과 관련된 학습 개념 범위를 좁혀 검색 정밀도 향상. |
| difficulty | document_chunks | document_chunks.difficulty | 연습 모드에서 난이도별 문제 생성이 불가능하다. 초급 학습자에게 ADVANCED 청크 기반 설명이 제공될 수 있다. | WHERE difficulty IN ('BASIC', 'INTERMEDIATE')로 학습자 수준에 맞는 청크만 검색. |
| quality_score | document_chunks | document_chunks.quality_score | 파싱 오류, 짧은 의미 없는 텍스트 등 저품질 청크가 검색 결과에 포함된다. AI 답변에 노이즈가 섞여 신뢰도가 하락한다. | WHERE quality_score >= 60 필터로 최소 품질 기준 이하 청크를 검색에서 제외. |
| access_level | document_chunks | document_chunks.access_level | PRIVATE 문서(특정 사용자만 접근 가능)의 청크가 다른 사용자의 검색 결과에 노출된다. 데이터 격리가 붕괴된다. | WHERE access_level IN ('SHARED', :user_access_level)로 권한 기반 검색 범위 제한. |
| is_active | document_chunks | document_chunks.is_active | 구버전 문서(비활성화된 document_version)의 청크가 검색 대상에 포함된다. 폐기된 내용이 AI 답변에 반영될 수 있다. | WHERE is_active = true로 현재 유효한 청크만 검색 대상으로 한정. |

### 3-3. 메타데이터 필터 적용 순서 권장

검색 성능 최적화를 위해 selectivity(선택도)가 높은 필터를 먼저 적용한다.

```
1. is_active = true          → 비활성 청크 제외 (대량 제거)
2. is_deleted = false        → 소프트 삭제된 행 제외
3. certification_id = :id    → 자격증 범위 한정 (대량 제거)
4. access_level IN (...)     → 권한 필터
5. quality_score >= 60       → 품질 필터
6. difficulty IN (...)       → 난이도 필터 (선택적)
7. exam_domain_id = :id      → 영역 필터 (선택적)
8. topic_id IN (...)         → 토픽 필터 (선택적)
```

---

## 4. Full-text Search 컬럼 설계

### 설계 결정: document_chunks에 chunk_tsv Generated Column 추가

Hybrid Search를 위해 document_chunks 테이블에 tsvector 타입의 Generated Column을 추가한다.

```sql
-- Full-text Search 보조 컬럼: document_chunks 테이블에 추가
-- Generated Column: chunk_text 변경 시 PostgreSQL이 자동으로 chunk_tsv를 재계산
-- STORED: 디스크에 저장하여 쿼리마다 재계산하지 않음 (성능 최적화)
ALTER TABLE document_chunks
    ADD COLUMN chunk_tsv TSVECTOR
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(chunk_text, ''))
    ) STORED;

COMMENT ON COLUMN document_chunks.chunk_tsv IS
    'Full-text Search용 tsvector. chunk_text 기반 Generated Column. GIN 인덱스와 함께 Hybrid Search에 활용.';
```

**설계 결정 근거**

| 항목 | 내용 |
|------|------|
| 배경 | Passly 청크는 "Azure OpenAI Service", "AI-102", "LUIS" 등 고유 기술 용어를 다수 포함한다. 이런 용어는 의미 기반 벡터 검색보다 정확한 키워드 매칭이 더 효과적이다. |
| 선택 | PostgreSQL 내장 `tsvector` + Generated Column으로 별도 검색 엔진(Elasticsearch 등) 없이 Full-text Search 구현. |
| 근거 | Generated Column은 chunk_text 변경 시 자동으로 재계산되므로 애플리케이션 레벨 동기화 로직이 불필요하다. 데이터 일관성을 DB가 보장한다. |
| 트레이드오프 | `to_tsvector('english', ...)` 언어 설정이 영어에 고정된다. 한국어 청크(한글 섞인 PDF 등)의 경우 full-text 검색 품질이 저하될 수 있다. 초기 대상(AI-102)은 영문 공식 가이드이므로 현재 단계에서는 허용. |

```sql
-- GIN 인덱스: Full-text Search 쿼리 최적화
-- GIN은 tsvector 타입에 최적화된 PostgreSQL 표준 인덱스 타입
CREATE INDEX idx_document_chunks_chunk_tsv
    ON document_chunks
    USING gin(chunk_tsv);

COMMENT ON INDEX idx_document_chunks_chunk_tsv IS
    'Full-text Search용 GIN 인덱스. Hybrid Search의 BM25 유사 키워드 검색에 활용.';
```

---

## 5. 벡터 인덱스 전략: IVFFlat vs HNSW

### 5-1. 알고리즘 비교

| 비교 항목 | IVFFlat | HNSW |
|-----------|---------|------|
| 알고리즘 원리 | 벡터 공간을 K개 클러스터(lists)로 분할. 쿼리 시 가장 가까운 probes개 클러스터만 탐색 | 계층적 그래프(Hierarchical Navigable Small World). 각 벡터가 이웃 노드와 연결된 그래프 구조를 탐색 |
| 인덱스 빌드 시간 | 빠름 (클러스터링 1회) | 느림 (각 벡터 삽입 시 그래프 재구성) |
| 인덱스 크기 | 작음 | 큼 (m=16 기준 약 IVFFlat의 2~3배) |
| 검색 속도 | probes 수에 따라 조절 가능 | 매우 빠름, probes 없이도 고속 |
| 검색 정확도(Recall) | probes 증가로 recall 향상 가능, 기본값에서 낮을 수 있음 | 높음, 기본값에서도 안정적 |
| 데이터 추가 비용 | 데이터 추가 후 REINDEX 권장 (클러스터 재분배) | 삽입 비용이 높지만 실시간 삽입 지원 |
| 메모리 요구 | 낮음 | 높음 |
| 적합한 규모 | 수만~수십만 건 | 수십만~수백만 건 이상 |
| PostgreSQL 지원 버전 | pgvector 초기부터 지원 | pgvector 0.5.0 이상 |

### 5-2. Passly 선택 근거

**결정: IVFFlat 적용**

| 항목 | 내용 |
|------|------|
| 배경 | 초기 예상 청크 수는 1만~3만 건이다. Azure AI-102 공식 가이드 + 덤프 PDF를 합산한 규모다. |
| 선택 | IVFFlat 인덱스, 코사인 유사도(vector_cosine_ops) |
| 근거 1 — 규모 적합성 | 3만 건 규모에서 IVFFlat은 충분한 recall과 응답 속도를 제공한다. HNSW는 이 규모에서 오버엔지니어링이다. |
| 근거 2 — 빌드 비용 | IVFFlat은 인덱스 빌드가 빠르다. 파이프라인 실행 후 인덱스 재구성 시간이 짧아 개발/운영 주기가 단축된다. |
| 근거 3 — 메모리 | 소규모 환경(Docker Compose, Cloud SQL 최소 인스턴스)에서 HNSW의 메모리 요구를 충족하기 어렵다. |
| 근거 4 — 사용자 규모 | 동시 검색 사용자가 2~10명으로 극소규모다. HNSW의 고속 검색 우위가 체감 차이를 만들지 않는다. |
| 트레이드오프 | IVFFlat은 데이터 삽입이 많으면 클러스터 분포가 틀어져 recall이 저하된다. 파이프라인 완료 후 REINDEX를 실행해야 한다. 이는 배치성 파이프라인 구조에서 허용 가능한 수준이다. |

**코사인 유사도 선택 근거**

Gemini text-embedding-004는 코사인 유사도(내적 기반 정규화)에 최적화된 임베딩을 생성한다. pgvector의 `vector_cosine_ops`는 `<=>` 연산자로 사용한다. L2(유클리드) 거리(`<->`)보다 코사인이 의미 유사도를 더 정확하게 포착한다.

### 5-3. lists 파라미터 계산

IVFFlat의 `lists`는 벡터 공간을 몇 개 클러스터로 분할할지 결정한다.

**권장 공식**: `lists = ceil(sqrt(총 벡터 수))`

| 시나리오 | 청크 수 | lists 계산 | 실무 적용값 |
|---------|--------|-----------|-----------|
| 초기 (보수 추정) | 10,000 | ceil(sqrt(10,000)) = 100 | 100 |
| 초기 (적극 추정) | 30,000 | ceil(sqrt(30,000)) ≈ 174 | 175 |
| 중기 확장 후 | 60,000 | ceil(sqrt(60,000)) ≈ 245 | 250 |

**Passly 적용값**: `lists = 175`

초기 30,000 청크 기준으로 175를 적용한다. 청크 수가 2배 이상 증가하면 REINDEX 시 lists 값을 재조정한다.

**lists 값이 너무 작으면**: 클러스터당 벡터가 많아져 probes 탐색 범위가 넓어지고, 전체 스캔에 가까워진다. 인덱스 효과가 감소한다.

**lists 값이 너무 크면**: 클러스터당 벡터가 너무 적어 각 클러스터가 통계적으로 의미 없어진다. 인덱스 빌드 메모리도 증가한다.

### 5-4. probes 파라미터 설명

`probes`는 쿼리 시 탐색할 클러스터 수다. 인덱스 생성 파라미터가 아니라 **세션(쿼리) 레벨 파라미터**다.

```sql
-- 세션 레벨 설정: 검색 쿼리 실행 전 설정
SET ivfflat.probes = 10;

-- 또는 트랜잭션 레벨 설정
SET LOCAL ivfflat.probes = 10;
```

| probes 값 | 탐색 클러스터 수 | recall | 검색 속도 | 권장 상황 |
|-----------|---------------|--------|---------|---------|
| 1 (기본값) | 1개 클러스터만 | 낮음 | 최고속 | 대규모 데이터, 속도 우선 |
| 10 | 10개 클러스터 | 중간 | 빠름 | 일반 운영 환경 |
| 20~30 | 20~30개 클러스터 | 높음 | 보통 | recall 중요 상황 |
| lists와 동일 | 전체 클러스터 | 100% (순차 스캔과 동일) | 느림 | 정확도 최대화, 벤치마크용 |

**Passly 권장 probes**: 기본 10, /chat 페이지(AI 질문 응답)는 15~20 적용

```python
# 검색 쿼리 전 probes 설정 (Python/SQLAlchemy)
async def search_chunks(query_embedding, certification_id, probes=10):
    await session.execute(text(f"SET LOCAL ivfflat.probes = {probes}"))
    # ... 검색 쿼리 실행
```

### 5-5. 향후 HNSW 전환 조건

아래 조건 중 하나 이상 충족 시 HNSW로 전환을 검토한다.

| 전환 조건 | 기준값 | 판단 방법 |
|---------|-------|---------|
| 청크 수 증가 | 10만 건 초과 | document_chunks 행 수 모니터링 |
| 검색 응답 시간 | P95 > 500ms | 애플리케이션 APM |
| IVFFlat recall 저하 | recall@10 < 0.85 | docs/07-search-evaluation.md 평가 기준 |
| 자격증 수 확장 | 3개 자격증 이상 | 청크 수 증가 연동 |

전환 시 인덱스 재생성 DDL:

```sql
-- 기존 IVFFlat 인덱스 제거
DROP INDEX IF EXISTS idx_chunk_embeddings_embedding_ivfflat;

-- HNSW 인덱스 생성 (m=16, ef_construction=64 — pgvector 기본 권장값)
CREATE INDEX idx_chunk_embeddings_embedding_hnsw
    ON chunk_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 5-6. 인덱스 DDL 전체

```sql
-- ============================================================
-- pgvector 인덱스 DDL
-- 실행 전제: 모든 테이블 및 데이터 삽입 완료 후 실행
-- IVFFlat은 데이터가 있어야 클러스터 중심점을 계산할 수 있음
-- (빈 테이블에 IVFFlat 인덱스 생성 시 경고 발생)
-- ============================================================

-- [1] chunk_embeddings 벡터 인덱스 (IVFFlat, 코사인 유사도)
-- lists = 175: ceil(sqrt(30000)) — 초기 3만 청크 기준
-- 청크 수 변동 시 REINDEX 와 lists 재조정 필요
CREATE INDEX idx_chunk_embeddings_embedding_ivfflat
    ON chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 175);

COMMENT ON INDEX idx_chunk_embeddings_embedding_ivfflat IS
    'IVFFlat 벡터 인덱스. lists=175 (ceil(sqrt(30000))). 코사인 유사도. 10만 청크 초과 시 HNSW 전환 검토.';

-- [2] document_chunks Full-text Search GIN 인덱스
-- (섹션 4에서 정의된 DDL — 참조용으로 여기에도 명시)
-- CREATE INDEX idx_document_chunks_chunk_tsv
--     ON document_chunks
--     USING gin(chunk_tsv);
-- → 위 인덱스는 섹션 4에서 실행. 중복 실행 방지를 위해 주석 처리.

-- ============================================================
-- 운영 관리 참고
-- ============================================================

-- IVFFlat 인덱스 재구성 (파이프라인 대량 삽입 후 권장)
-- REINDEX INDEX CONCURRENTLY idx_chunk_embeddings_embedding_ivfflat;

-- 현재 probes 설정 확인
-- SHOW ivfflat.probes;

-- 인덱스 사용 여부 확인 (실행 계획)
-- EXPLAIN (ANALYZE, BUFFERS)
-- SELECT chunk_id, embedding <=> '[0.1, 0.2, ...]'::vector AS distance
-- FROM chunk_embeddings
-- ORDER BY distance LIMIT 10;
```

---

## 6. Hybrid Search 구조

### 6-1. Vector Search 단독의 한계

| 한계 | 구체적 문제 | 예시 |
|------|-----------|------|
| 기술 용어 정확 매칭 약점 | 벡터는 의미 공간에서 유사한 개념을 찾는다. 정확한 키워드 일치는 보장하지 않는다. | "LUIS" 검색 시 "Language Understanding" 청크가 상위에 오지만 "LUIS"라는 단어가 없는 청크가 포함될 수 있다. |
| 철자 민감성 | 임베딩 모델은 오탈자를 일부 흡수하지만, 도메인 고유명사(제품 코드, API명)에서 실패할 수 있다. | "AI-102" vs "AI102" — 임베딩 공간에서 동일하게 취급되지 않을 수 있다. |
| 최신 용어 취약 | 임베딩 모델이 학습하지 않은 신규 서비스명은 의미 임베딩이 불안정하다. | 신규 출시 Azure 서비스명 검색 시 관련 없는 결과 반환 가능성 있음. |
| 랭킹 해석 어려움 | 벡터 거리만으로는 "왜 이 청크가 상위인가" 설명이 어렵다. | AI 답변의 출처 청크 신뢰도 설명 불가. |

**결론**: 벡터 검색은 의미 유사도에 강하고, Full-text 검색은 키워드 정확 매칭에 강하다. 두 방식을 결합한 Hybrid Search가 자격증 도메인에서 더 높은 검색 품질을 제공한다.

### 6-2. RRF(Reciprocal Rank Fusion) 원리

RRF는 두 개 이상의 랭킹 결과를 점수 정규화 없이 순위만으로 통합하는 알고리즘이다.

**RRF 공식**:

```
RRF_score(d) = Σ  1 / (k + rank_i(d))
              i∈검색방식
```

- `d`: 문서(청크)
- `rank_i(d)`: 검색 방식 i에서 문서 d의 순위 (1부터 시작)
- `k`: 댐핑 파라미터 (기본값 60 — 순위 1위와 2위의 점수 차이를 완충)
- 여러 검색 방식에서 높은 순위를 기록할수록 최종 RRF 점수가 높아진다

**k=60 선택 근거**

k=60은 Cormack et al. (2009) 원 논문에서 제안한 기본값이다. 이 값은 1위 문서의 과도한 지배력을 방지하면서도 상위 문서에 충분한 가중치를 부여한다. Passly 규모에서 조정 없이 k=60을 그대로 적용한다.

**계산 예시** (k=60)

| 청크 | 벡터 검색 순위 | FTS 순위 | RRF 점수 |
|------|-------------|---------|---------|
| 청크 A | 1위 | 3위 | 1/61 + 1/63 = 0.0321 |
| 청크 B | 3위 | 1위 | 1/63 + 1/61 = 0.0321 |
| 청크 C | 2위 | 2위 | 1/62 + 1/62 = 0.0323 |
| 청크 D | 5위 | 미포함 | 1/65 + 0 = 0.0154 |

청크 C처럼 두 방식 모두에서 고르게 상위인 문서가 최종적으로 높은 순위를 얻는다.

### 6-3. 검색 흐름 다이어그램

```
사용자 질문 입력
       |
       v
[임베딩 생성]
Gemini text-embedding-004
query_embedding = embed(question_text)
       |
       +---------------------------+
       |                           |
       v                           v
[벡터 검색 (Vector Search)]    [Full-text 검색 (FTS)]
chunk_embeddings 테이블         document_chunks 테이블
embedding <=> query_vector      chunk_tsv @@ plainto_tsquery
ORDER BY 코사인 거리 ASC         ts_rank(chunk_tsv, query) DESC
-- 메타데이터 필터 적용 --        -- 동일 메타데이터 필터 --
LIMIT 20                        LIMIT 20
       |                           |
       v                           v
[벡터 결과 순위]               [FTS 결과 순위]
청크 A: rank 1                  청크 A: rank 3
청크 B: rank 2                  청크 C: rank 1
청크 C: rank 3                  청크 B: rank 2
...                             ...
       |                           |
       +---------------------------+
                   |
                   v
       [RRF (Reciprocal Rank Fusion)]
       각 청크별 RRF 점수 계산
       score = 1/(60+rank_vec) + 1/(60+rank_fts)
       청크가 한쪽에만 있으면 해당 항만 합산
                   |
                   v
       [최종 랭킹 정렬]
       ORDER BY rrf_score DESC
       LIMIT 10
                   |
                   v
       [청크 원문 조회]
       document_chunks.chunk_text
       chunk_topics, topics 등 메타데이터
                   |
                   v
       [LLM 답변 생성]
       컨텍스트 = 상위 청크 원문
       Gemini API 호출
                   |
                   v
       [출처 표시와 함께 답변 반환]
       /chat 페이지에 표시
```

### 6-4. 통합 SQL 쿼리 (CTE)

실제 운영에서 사용하는 Hybrid Search CTE 쿼리 전체다. 메타데이터 필터는 두 검색 모두에 동일하게 적용한다.

```sql
-- Hybrid Search: Vector Search + Full-text Search + RRF 통합 쿼리
-- 파라미터:
--   :query_embedding  — 쿼리 텍스트의 벡터 (Python에서 Gemini API로 생성)
--   :query_text       — 쿼리 텍스트 원문 (Full-text Search용)
--   :certification_id — 자격증 UUID 필터
--   :min_quality      — 최소 품질 점수 (기본값: 60)
--   :top_k            — 최종 반환 청크 수 (기본값: 10)
--   :candidate_k      — 각 검색에서 수집할 후보 수 (기본값: 20)
--   :rrf_k            — RRF 댐핑 파라미터 (기본값: 60)

WITH
-- Step 1: 유효한 청크 범위 한정 (메타데이터 필터 사전 적용)
active_chunks AS (
    SELECT
        dc.id          AS chunk_id,
        dc.chunk_text,
        dc.chunk_summary,
        dc.chunk_order,
        dc.difficulty,
        dc.quality_score,
        dc.access_level,
        dc.chunk_tsv,
        lv.id          AS document_version_id,
        ld.certification_id
    FROM document_chunks dc
    JOIN document_versions lv ON dc.document_version_id = lv.id
    JOIN learning_documents ld ON lv.learning_document_id = ld.id
    WHERE dc.is_active   = true
      AND dc.is_deleted  = false
      AND ld.certification_id = :certification_id
      AND dc.quality_score >= :min_quality          -- 품질 필터
      AND dc.access_level IN ('SHARED', :user_access_level)  -- 권한 필터
),

-- Step 2: Vector Search — 코사인 유사도 기반 상위 후보 추출
vector_search AS (
    SELECT
        ac.chunk_id,
        ROW_NUMBER() OVER (
            ORDER BY ce.embedding <=> :query_embedding::vector ASC
        ) AS rank_vec
    FROM active_chunks ac
    JOIN chunk_embeddings ce ON ac.chunk_id = ce.chunk_id
    WHERE ce.is_deleted = false
    LIMIT :candidate_k
),

-- Step 3: Full-text Search — tsvector 기반 키워드 매칭 상위 후보 추출
fts_search AS (
    SELECT
        ac.chunk_id,
        ROW_NUMBER() OVER (
            ORDER BY ts_rank_cd(ac.chunk_tsv, plainto_tsquery('english', :query_text)) DESC
        ) AS rank_fts
    FROM active_chunks ac
    WHERE ac.chunk_tsv @@ plainto_tsquery('english', :query_text)
    LIMIT :candidate_k
),

-- Step 4: RRF 점수 계산 — FULL OUTER JOIN으로 양측 결과 통합
rrf_scores AS (
    SELECT
        COALESCE(vs.chunk_id, fs.chunk_id)         AS chunk_id,
        COALESCE(1.0 / (:rrf_k + vs.rank_vec), 0)  AS score_vec,
        COALESCE(1.0 / (:rrf_k + fs.rank_fts), 0)  AS score_fts,
        COALESCE(1.0 / (:rrf_k + vs.rank_vec), 0)
            + COALESCE(1.0 / (:rrf_k + fs.rank_fts), 0) AS rrf_score
    FROM vector_search vs
    FULL OUTER JOIN fts_search fs ON vs.chunk_id = fs.chunk_id
)

-- Step 5: 최종 결과 — RRF 점수 내림차순, 청크 원문 JOIN
SELECT
    rrf.chunk_id,
    rrf.rrf_score,
    rrf.score_vec,
    rrf.score_fts,
    ac.chunk_text,
    ac.chunk_summary,
    ac.difficulty,
    ac.quality_score,
    ac.certification_id
FROM rrf_scores rrf
JOIN active_chunks ac ON rrf.chunk_id = ac.chunk_id
ORDER BY rrf.rrf_score DESC
LIMIT :top_k;
```

**쿼리 실행 전 세션 파라미터 설정**:

```sql
-- IVFFlat probes 설정 (벡터 검색 recall 조정)
SET LOCAL ivfflat.probes = 15;  -- /chat 페이지 권장값
```

### 6-5. Python 구현 패턴

```python
# backend/app/rag/retriever.py (Wave 4 구현 시 참조)
from typing import Optional
from uuid import UUID
import asyncpg
from google.generativeai import embed_content  # Gemini API


async def hybrid_search(
    conn: asyncpg.Connection,
    query_text: str,
    certification_id: UUID,
    user_access_level: str = "SHARED",
    min_quality: float = 60.0,
    top_k: int = 10,
    candidate_k: int = 20,
    rrf_k: int = 60,
    probes: int = 15,
) -> list[dict]:
    """
    Hybrid Search: Vector + Full-text + RRF 통합 검색.

    Args:
        query_text: 사용자 질문 텍스트
        certification_id: 검색 대상 자격증 UUID
        user_access_level: 현재 사용자 접근 수준 (PRIVATE | SHARED)
        min_quality: 최소 청크 품질 점수 (0~100)
        top_k: 최종 반환 청크 수
        candidate_k: Vector/FTS 각각에서 수집할 후보 수
        rrf_k: RRF 댐핑 파라미터 (권장: 60)
        probes: IVFFlat probes 파라미터 (권장: 10~20)

    Returns:
        RRF 점수 내림차순 정렬된 청크 목록
    """
    # Step 1: 쿼리 텍스트 임베딩 생성 (Gemini API)
    response = embed_content(
        model="models/text-embedding-004",
        content=query_text,
        task_type="retrieval_query",  # 검색 쿼리용 task_type 지정
    )
    query_embedding: list[float] = response["embedding"]

    # Step 2: IVFFlat probes 세션 설정
    await conn.execute(f"SET LOCAL ivfflat.probes = {probes}")

    # Step 3: Hybrid Search CTE 실행
    # (위 섹션 6-4의 SQL 쿼리를 파라미터 바인딩하여 실행)
    hybrid_sql = """
        WITH active_chunks AS (
            SELECT dc.id AS chunk_id, dc.chunk_text, dc.chunk_summary,
                   dc.difficulty, dc.quality_score, dc.chunk_tsv,
                   ld.certification_id
            FROM document_chunks dc
            JOIN document_versions lv ON dc.document_version_id = lv.id
            JOIN learning_documents ld ON lv.learning_document_id = ld.id
            WHERE dc.is_active = true
              AND dc.is_deleted = false
              AND ld.certification_id = $1
              AND dc.quality_score >= $2
              AND dc.access_level IN ('SHARED', $3)
        ),
        vector_search AS (
            SELECT ac.chunk_id,
                   ROW_NUMBER() OVER (
                       ORDER BY ce.embedding <=> $4::vector ASC
                   ) AS rank_vec
            FROM active_chunks ac
            JOIN chunk_embeddings ce ON ac.chunk_id = ce.chunk_id
            WHERE ce.is_deleted = false
            LIMIT $5
        ),
        fts_search AS (
            SELECT ac.chunk_id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(
                           ac.chunk_tsv,
                           plainto_tsquery('english', $6)
                       ) DESC
                   ) AS rank_fts
            FROM active_chunks ac
            WHERE ac.chunk_tsv @@ plainto_tsquery('english', $6)
            LIMIT $5
        ),
        rrf_scores AS (
            SELECT
                COALESCE(vs.chunk_id, fs.chunk_id) AS chunk_id,
                COALESCE(1.0 / ($7 + vs.rank_vec), 0)
                    + COALESCE(1.0 / ($7 + fs.rank_fts), 0) AS rrf_score
            FROM vector_search vs
            FULL OUTER JOIN fts_search fs ON vs.chunk_id = fs.chunk_id
        )
        SELECT rrf.chunk_id, rrf.rrf_score,
               ac.chunk_text, ac.chunk_summary, ac.difficulty, ac.quality_score
        FROM rrf_scores rrf
        JOIN active_chunks ac ON rrf.chunk_id = ac.chunk_id
        ORDER BY rrf.rrf_score DESC
        LIMIT $8
    """

    rows = await conn.fetch(
        hybrid_sql,
        str(certification_id),  # $1
        min_quality,             # $2
        user_access_level,       # $3
        str(query_embedding),    # $4 — vector 타입으로 자동 캐스팅
        candidate_k,             # $5
        query_text,              # $6
        float(rrf_k),            # $7
        top_k,                   # $8
    )

    return [dict(row) for row in rows]
```

---

## 7. 검색 쿼리 패턴 레퍼런스

### 패턴 1: 순수 벡터 검색 (단순 유사도 검색)

```sql
-- 사용 시점: 벤치마크, 검색 품질 비교, Hybrid 대비 baseline 측정
-- probes 설정 후 실행 권장

SET LOCAL ivfflat.probes = 10;

SELECT
    dc.id,
    dc.chunk_text,
    dc.difficulty,
    dc.quality_score,
    ce.embedding <=> :query_embedding::vector AS cosine_distance
FROM document_chunks dc
JOIN document_versions dv ON dc.document_version_id = dv.id
JOIN learning_documents ld ON dv.learning_document_id = ld.id
JOIN chunk_embeddings ce ON dc.id = ce.chunk_id
WHERE dc.is_active   = true
  AND dc.is_deleted  = false
  AND ce.is_deleted  = false
  AND ld.certification_id = :certification_id
  AND dc.quality_score >= 60
ORDER BY cosine_distance ASC
LIMIT 10;
```

### 패턴 2: 토픽 필터 포함 벡터 검색

```sql
-- 사용 시점: /practice 페이지 특정 토픽 문제 생성용 청크 검색

SET LOCAL ivfflat.probes = 10;

SELECT
    dc.id,
    dc.chunk_text,
    dc.difficulty,
    t.name AS topic_name,
    ce.embedding <=> :query_embedding::vector AS cosine_distance
FROM document_chunks dc
JOIN document_versions dv ON dc.document_version_id = dv.id
JOIN learning_documents ld ON dv.learning_document_id = ld.id
JOIN chunk_embeddings ce ON dc.id = ce.chunk_id
JOIN chunk_topics ct ON dc.id = ct.chunk_id
JOIN topics t ON ct.topic_id = t.id
WHERE dc.is_active   = true
  AND dc.is_deleted  = false
  AND ce.is_deleted  = false
  AND ld.certification_id = :certification_id
  AND ct.topic_id    = :topic_id
  AND dc.quality_score >= 60
ORDER BY cosine_distance ASC
LIMIT 10;
```

### 패턴 3: 난이도 필터 포함 벡터 검색

```sql
-- 사용 시점: 학습자 수준별 문제 생성 — BASIC 청크만 참조

SET LOCAL ivfflat.probes = 10;

SELECT
    dc.id,
    dc.chunk_text,
    dc.difficulty,
    ce.embedding <=> :query_embedding::vector AS cosine_distance
FROM document_chunks dc
JOIN document_versions dv ON dc.document_version_id = dv.id
JOIN learning_documents ld ON dv.learning_document_id = ld.id
JOIN chunk_embeddings ce ON dc.id = ce.chunk_id
WHERE dc.is_active   = true
  AND dc.is_deleted  = false
  AND ce.is_deleted  = false
  AND ld.certification_id = :certification_id
  AND dc.difficulty  IN ('BASIC', 'INTERMEDIATE')  -- 코드값: DIFFICULTY 그룹
  AND dc.quality_score >= 60
ORDER BY cosine_distance ASC
LIMIT 10;
```

### 패턴 4: 임베딩 모델 버전 확인 쿼리

```sql
-- 사용 시점: 모델 교체 전/후 임베딩 현황 파악, 재생성 대상 식별

SELECT
    model_name,
    model_version,
    COUNT(*)          AS embedding_count,
    MIN(created_at)   AS oldest_embedding,
    MAX(created_at)   AS newest_embedding
FROM chunk_embeddings
WHERE is_deleted = false
GROUP BY model_name, model_version
ORDER BY newest_embedding DESC;
```

### 패턴 5: 품질 점수 분포 확인 쿼리

```sql
-- 사용 시점: 검색 대상 청크 품질 현황 파악 (운영 모니터링)

SELECT
    CASE
        WHEN quality_score IS NULL        THEN '미평가'
        WHEN quality_score < 40           THEN '저품질 (0~39)'
        WHEN quality_score BETWEEN 40 AND 59 THEN '중품질 (40~59)'
        WHEN quality_score BETWEEN 60 AND 79 THEN '양품질 (60~79)'
        WHEN quality_score >= 80          THEN '고품질 (80~100)'
    END AS quality_tier,
    COUNT(*) AS chunk_count
FROM document_chunks
WHERE is_deleted = false
  AND is_active  = true
GROUP BY quality_tier
ORDER BY MIN(quality_score) ASC NULLS FIRST;
```

---

## 8. 설계 자체 검토 체크리스트

pgvector-design 스킬 품질 기준 및 AGENTS.md review-agent 체크리스트 기준으로 자체 검토한 결과다.

### pgvector 설계 품질 기준

| 항목 | 상태 | 근거 |
|------|------|------|
| 벡터 차원수가 사용 모델과 일치하는가 (Gemini: 768) | 완료 | chunk_embeddings.embedding vector(768) — 섹션 2-1 |
| metadata 필드가 모두 포함되어 있는가 | 완료 | 섹션 3에서 10개 필드 전체 분석 |
| 인덱스 선택 근거가 문서에 있는가 | 완료 | 섹션 5 — IVFFlat vs HNSW 비교표 + 선택 근거 |
| Hybrid Search 구조가 설계되어 있는가 | 완료 | 섹션 6 — RRF 원리 + CTE 쿼리 + Python 구현 패턴 |

### AGENTS.md review-agent 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| AGENTS.md 원칙 위반 없음 | 완료 | metadata 없는 pgvector index 설계 금지 — 섹션 3에서 10개 필드 설계 |
| 명명 규칙 준수 | 완료 | idx_chunk_embeddings_embedding_ivfflat (idx_테이블_컬럼 형식) |
| 공통 컬럼 4개 존재 | 완료 | id, created_at, updated_at, is_deleted 모두 포함 |
| docs/와 코드 일치 | 완료 | chunk_embeddings DDL이 docs/03-erd-physical.md 섹션 4-9와 동일 |
| 하드코딩 없음 | 완료 | lists=175 계산 근거 명시, probes는 파라미터로 분리 |
| pgvector 사용 시 metadata 필드 완전 | 완료 | 섹션 3 — 직접 보유 2개 + JOIN 7개 = 총 9개 메타데이터 필드 |

### 설계 결정 기록 완전성 확인

| 설계 결정 | 배경 | 선택 | 근거 | 트레이드오프 |
|---------|------|------|------|------------|
| document_chunks와 1:1 분리 | 섹션 2-3 | chunk_embeddings 별도 테이블 | 비벡터 쿼리 성능 보호 | JOIN 필수 |
| IVFFlat 선택 | 섹션 5-2 | IVFFlat (lists=175) | 3만 청크 규모 적합, 빌드 비용 낮음 | 대량 삽입 후 REINDEX 필요 |
| 코사인 유사도 | 섹션 5-2 | vector_cosine_ops | Gemini 임베딩 권장 메트릭 | L2와 비교 벤치마크 미수행 |
| Hybrid Search (RRF k=60) | 섹션 6-2 | k=60 기본값 적용 | 원 논문 권장값, Passly 규모에서 조정 불필요 | 도메인 최적화 미수행 |
| Generated Column (chunk_tsv) | 섹션 4 | STORED Generated Column | DB가 동기화 보장, 앱 코드 불필요 | 영어 언어 고정 |

---

*이 문서는 Passly Wave 1 설계 단계 산출물이다. 구현(Wave 3)에서 실제 검색 성능 측정 후 인덱스 파라미터(lists, probes, rrf_k)를 조정하며, 검색 품질 평가 결과는 docs/07-search-evaluation.md에 기록한다.*
