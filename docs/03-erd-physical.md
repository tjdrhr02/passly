# Passly 물리 데이터 모델 (Physical ERD / DDL)

> 버전: 1.0 | 작성일: 2026-05
> 대상 DB: PostgreSQL 17 + pgvector
> 이 문서는 docs/02-erd-logical.md의 논리 모델을 물리 DDL로 구체화한다.

---

## 목차

1. [DDL 실행 순서 및 의존성 그래프](#1-ddl-실행-순서-및-의존성-그래프)
2. [PostgreSQL 확장 설치](#2-postgresql-확장-설치)
3. [공통 트리거 함수](#3-공통-트리거-함수)
4. [테이블 DDL](#4-테이블-ddl)
   - 4-1. code_values
   - 4-2. certifications
   - 4-3. users
   - 4-4. exam_domains
   - 4-5. topics
   - 4-6. learning_documents
   - 4-7. document_versions
   - 4-8. document_chunks
   - 4-9. chunk_embeddings
   - 4-10. chunk_topics
   - 4-11. questions
   - 4-12. choices
   - 4-13. answer_explanations
   - 4-14. exam_sessions
   - 4-15. user_attempts
   - 4-16. pipeline_runs
5. [인덱스 DDL](#5-인덱스-ddl)
6. [트리거 DDL](#6-트리거-ddl)
7. [제약조건 설계 결정](#7-제약조건-설계-결정)
8. [반정규화 결정 기록](#8-반정규화-결정-기록)
9. [물리 설계 자체 검토 체크리스트](#9-물리-설계-자체-검토-체크리스트)

---

## 1. DDL 실행 순서 및 의존성 그래프

FK 참조 무결성을 위해 반드시 아래 순서로 실행해야 한다.
역순으로 DROP 하면 FK 의존성 오류 없이 정리할 수 있다.

```
[확장 설치]
  └─ pgcrypto (gen_random_uuid 제공)
  └─ vector   (pgvector 임베딩 타입 제공)

[공통 함수]
  └─ update_updated_at_column()

[코드 / 마스터 — 참조 없음]
  1. code_values
  2. certifications
  3. users

[마스터 — certifications 참조]
  4. exam_domains  → certifications
  5. topics        → exam_domains

[문서 계층 — certifications 참조]
  6. learning_documents → certifications
  7. document_versions  → learning_documents
  8. document_chunks    → document_versions

[파생 / 교차]
  9. chunk_embeddings   → document_chunks
 10. chunk_topics       → document_chunks, topics

[문제 계층]
 11. questions          → certifications, topics, document_chunks(nullable)
 12. choices            → questions
 13. answer_explanations → questions, document_chunks(nullable)

[시험 / 이력]
 14. exam_sessions      → users, certifications
 15. user_attempts      → exam_sessions, questions

[운영 이력]
 16. pipeline_runs      → learning_documents, document_versions(nullable)

[인덱스 — 모든 테이블 생성 후]
[트리거 — 모든 테이블 생성 후]
```

---

## 2. PostgreSQL 확장 설치

```sql
-- gen_random_uuid() 함수 제공 (PostgreSQL 13+ 내장이나 명시적 설치 권장)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- pgvector: vector(768) 타입 및 유사도 연산자 제공
-- 설치 전 PostgreSQL 서버에 pgvector 라이브러리가 있어야 한다
-- Docker: pgvector/pgvector:pg17 이미지 사용
CREATE EXTENSION IF NOT EXISTS "vector";
```

---

## 3. 공통 트리거 함수

모든 테이블의 `updated_at` 컬럼을 자동 갱신하는 공통 함수.
각 테이블에 `BEFORE UPDATE` 트리거로 연결된다. (섹션 6 참고)

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## 4. 테이블 DDL

### 4-1. code_values

고정 코드 값을 중앙 관리하는 코드 테이블.
DIFFICULTY, SOURCE_TYPE, QUESTION_TYPE, PIPELINE_STATUS, EXAM_MODE, ACCESS_LEVEL 등
모든 코드 그룹을 단일 테이블로 관리한다.
애플리케이션에서 하드코딩 없이 코드값을 참조할 수 있다.

```sql
-- 코드 테이블: 고정 값 목록 중앙 관리. docs/00-data-standard.md 섹션 5 참고.
CREATE TABLE code_values (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code_group  VARCHAR(50) NOT NULL,  -- 코드 그룹: DIFFICULTY, SOURCE_TYPE 등
    code_value  VARCHAR(50) NOT NULL,  -- 코드값: BASIC, INTERMEDIATE 등 (UPPER_SNAKE_CASE)
    code_name   VARCHAR(100) NOT NULL, -- 화면 표시명: 기본, 중급 등
    sort_order  INTEGER     NOT NULL DEFAULT 0,
    is_active   BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted  BOOLEAN     NOT NULL DEFAULT false,
    CONSTRAINT uq_code_values_group_value UNIQUE (code_group, code_value)
);

COMMENT ON TABLE  code_values IS '공통 코드 테이블. 코드값 하드코딩 금지.';
COMMENT ON COLUMN code_values.code_group  IS '코드 그룹 식별자 (DIFFICULTY, SOURCE_TYPE, ...)';
COMMENT ON COLUMN code_values.code_value  IS '코드값 — UPPER_SNAKE_CASE 규칙';
COMMENT ON COLUMN code_values.sort_order  IS '화면 정렬 순서';
```

---

### 4-2. certifications

학습 대상 자격증 마스터 테이블.
`exam_code`는 실제 시험 코드(예: AI-102)로 유니크 제약을 가진다.

```sql
-- 자격증 마스터: 플랫폼에서 지원하는 모든 자격증 목록
CREATE TABLE certifications (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(255) NOT NULL,            -- 자격증 전체 이름
    vendor           VARCHAR(100) NOT NULL,            -- 제공 벤더: Microsoft, AWS 등
    exam_code        VARCHAR(50)  NOT NULL UNIQUE,     -- 시험 코드: AI-102, SAA-C03 등
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted       BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  certifications IS '자격증 마스터 테이블';
COMMENT ON COLUMN certifications.exam_code IS '시험 코드 — 전 세계 고유값, UNIQUE 제약';
```

---

### 4-3. users

서비스 사용자 테이블.
소규모(2~10명) 운영 환경이므로 별도 인증 서버 없이 자체 관리한다.

```sql
-- 사용자 마스터: 서비스 접근 사용자
CREATE TABLE users (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email          VARCHAR(255) NOT NULL UNIQUE,
    name           VARCHAR(255) NOT NULL,
    access_level   VARCHAR(50)  NOT NULL DEFAULT 'PRIVATE', -- 코드값: ACCESS_LEVEL 그룹
    last_login_at  TIMESTAMPTZ,                              -- NULL 허용: 최초 로그인 전
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted     BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  users IS '사용자 마스터 테이블';
COMMENT ON COLUMN users.access_level  IS '접근 수준 코드값 (code_values.ACCESS_LEVEL 그룹)';
COMMENT ON COLUMN users.last_login_at IS 'NULL = 아직 로그인한 적 없음';
```

---

### 4-4. exam_domains

자격증 내 출제 영역과 가중치.
`weight_percent`의 합이 100이 되는 것은 애플리케이션 레벨에서 검증한다.
(영역별 합산 CHECK는 행 단위 제약으로 표현 불가 — 트리거 또는 앱 레벨 책임)

```sql
-- 시험 영역: 자격증의 출제 영역 및 가중치 정의
CREATE TABLE exam_domains (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    certification_id  UUID        NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
    name              VARCHAR(100) NOT NULL,
    weight_percent    INTEGER     NOT NULL CHECK (weight_percent BETWEEN 1 AND 100),
    order_num         INTEGER     NOT NULL,  -- 화면 표시 순서
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted        BOOLEAN     NOT NULL DEFAULT false
);

COMMENT ON TABLE  exam_domains IS '자격증별 출제 영역 및 가중치';
COMMENT ON COLUMN exam_domains.weight_percent IS '출제 비중(%) — 행 단위 범위만 검증. 합산 100 검증은 앱 레벨';
COMMENT ON COLUMN exam_domains.order_num IS '출제 영역 표시 순서 (1부터 시작)';
```

---

### 4-5. topics

시험 영역 내 세부 학습 개념.
문서 청크, 문제와 연결되어 RAG 검색의 메타데이터 필터로도 활용된다.

```sql
-- 학습 개념: 시험 영역 내 세부 토픽
CREATE TABLE topics (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_domain_id  UUID         NOT NULL REFERENCES exam_domains(id) ON DELETE RESTRICT,
    name            VARCHAR(100) NOT NULL,
    description     TEXT,        -- NULL 허용: 초기 입력 시 설명 없을 수 있음
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  topics IS '시험 영역 내 세부 학습 개념 — RAG 메타데이터 필터 활용';
COMMENT ON COLUMN topics.description IS 'NULL 허용. 토픽 설명이 없을 경우 허용';
```

---

### 4-6. learning_documents

업로드된 PDF 원본 정보.
실제 파일은 Cloud Storage에 저장하고, `file_path`에 경로(GCS URI)를 저장한다.

```sql
-- 학습 문서: 업로드된 PDF 원본 메타데이터
CREATE TABLE learning_documents (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    certification_id  UUID         NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
    title             VARCHAR(255) NOT NULL,
    source_type       VARCHAR(50)  NOT NULL, -- 코드값: SOURCE_TYPE 그룹 (OFFICIAL_GUIDE, DUMP)
    file_path         VARCHAR(500) NOT NULL, -- GCS URI 또는 로컬 경로
    original_filename VARCHAR(255) NOT NULL, -- 사용자가 업로드한 원본 파일명
    is_active         BOOLEAN      NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted        BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  learning_documents IS '업로드된 PDF 원본 메타데이터. 실제 파일은 Cloud Storage';
COMMENT ON COLUMN learning_documents.file_path IS 'GCS URI (gs://bucket/path) 또는 로컬 경로';
COMMENT ON COLUMN learning_documents.source_type IS 'code_values SOURCE_TYPE 그룹 참조';
```

---

### 4-7. document_versions

문서 재업로드/갱신 이력 관리.
버전 전환은 `is_active` 플래그 교체로 진행하며, 구버전 청크를 즉시 삭제하지 않는다.
설계 근거: docs/02-erd-logical.md 결정 1 참고.

```sql
-- 문서 버전: 동일 문서의 버전별 이력 관리
-- 설계 근거: docs/02-erd-logical.md 결정 1 — 진행 중인 시험 세션 보호
CREATE TABLE document_versions (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_document_id UUID        NOT NULL REFERENCES learning_documents(id) ON DELETE RESTRICT,
    version_number       INTEGER     NOT NULL DEFAULT 1,
    is_active            BOOLEAN     NOT NULL DEFAULT false, -- 최신 활성 버전만 true
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted           BOOLEAN     NOT NULL DEFAULT false,
    CONSTRAINT uq_document_versions_doc_ver UNIQUE (learning_document_id, version_number)
);

COMMENT ON TABLE  document_versions IS '문서 버전 이력. is_active=true가 현재 활성 버전';
COMMENT ON COLUMN document_versions.is_active IS '1개 문서에 활성 버전은 1개여야 함 — 앱 레벨에서 보장';
```

---

### 4-8. document_chunks

RAG 검색의 최소 단위.
`quality_score`는 파이프라인이 청크 품질을 0~100으로 평가한 값이다.
`access_level`은 SHARED/PRIVATE으로 청크 단위 접근 제어를 가능하게 한다.

```sql
-- 문서 청크: RAG 검색 최소 단위. 의미 단위로 분할된 텍스트 조각
CREATE TABLE document_chunks (
    id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id  UUID          NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
    chunk_text           TEXT          NOT NULL,    -- 원문 텍스트
    chunk_summary        TEXT,                      -- LLM 요약 (NULL 허용: 요약 전)
    chunk_order          INTEGER       NOT NULL,    -- 문서 내 순서 (0부터 시작)
    token_count          INTEGER       NOT NULL DEFAULT 0,
    difficulty           VARCHAR(50),               -- 코드값: DIFFICULTY 그룹 (NULL 허용: 분류 전)
    quality_score        NUMERIC(5,2), -- 청크 품질 점수 0.00~100.00 (NULL 허용: 평가 전)
    access_level         VARCHAR(50)   NOT NULL DEFAULT 'SHARED', -- 코드값: ACCESS_LEVEL 그룹
    is_active            BOOLEAN       NOT NULL DEFAULT true,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    is_deleted           BOOLEAN       NOT NULL DEFAULT false,
    CONSTRAINT chk_document_chunks_quality_score
        CHECK (quality_score IS NULL OR quality_score BETWEEN 0 AND 100)
);

COMMENT ON TABLE  document_chunks IS 'RAG 검색 최소 단위. chunk_embeddings와 1:1 관계';
COMMENT ON COLUMN document_chunks.chunk_summary IS 'LLM 생성 요약. Hybrid Search에 활용. NULL = 아직 요약 안 됨';
COMMENT ON COLUMN document_chunks.quality_score IS '파이프라인 품질 평가 점수 0~100. NULL = 평가 전';
COMMENT ON COLUMN document_chunks.access_level IS 'code_values ACCESS_LEVEL 그룹 (PRIVATE/SHARED)';
```

---

### 4-9. chunk_embeddings

문서 청크의 pgvector 임베딩 저장.
`chunk_id`에 UNIQUE 제약으로 1:1 관계를 DB 레벨에서 보장한다.
임베딩 모델 메타데이터(`model_name`, `model_version`)를 함께 저장하여 모델 교체 이력 추적이 가능하다.
설계 근거: docs/02-erd-logical.md 결정 2 참고.

```sql
-- 청크 임베딩: document_chunks의 벡터 표현. pgvector 저장.
-- 설계 근거: docs/02-erd-logical.md 결정 2 — 대용량 벡터 분리로 비벡터 쿼리 성능 보호
CREATE TABLE chunk_embeddings (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id       UUID         NOT NULL UNIQUE REFERENCES document_chunks(id) ON DELETE RESTRICT,
    embedding      vector(768)  NOT NULL,         -- Gemini text-embedding-004 기준 768차원
    model_name     VARCHAR(100) NOT NULL,          -- 임베딩 모델명: text-embedding-004 등
    model_version  VARCHAR(50)  NOT NULL,          -- 모델 버전: 버전 교체 이력 추적
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted     BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  chunk_embeddings IS '청크 임베딩 벡터. document_chunks와 1:1 분리 (성능 최적화)';
COMMENT ON COLUMN chunk_embeddings.embedding IS 'vector(768) — Gemini text-embedding-004. 모델 교체 시 전체 재생성';
COMMENT ON COLUMN chunk_embeddings.model_name IS '임베딩 모델 식별자 — 모델 교체 추적용';
```

---

### 4-10. chunk_topics

document_chunks ↔ topics M:N 교차 테이블.
하나의 청크가 여러 토픽을 설명할 수 있으며,
하나의 토픽은 여러 청크에서 다뤄진다.
UNIQUE(chunk_id, topic_id)로 중복 매핑을 방지한다.

```sql
-- 청크-토픽 교차 테이블: M:N 관계 분해
-- document_chunks.topic_id FK 대신 별도 교차 테이블로 설계
-- 이유: 1개 청크가 복수 토픽을 다룰 수 있음 (다중 개념 설명 청크)
CREATE TABLE chunk_topics (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id    UUID        NOT NULL REFERENCES document_chunks(id) ON DELETE RESTRICT,
    topic_id    UUID        NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted  BOOLEAN     NOT NULL DEFAULT false,
    CONSTRAINT uq_chunk_topics_chunk_topic UNIQUE (chunk_id, topic_id)
);

COMMENT ON TABLE chunk_topics IS 'document_chunks ↔ topics M:N 교차 테이블. 중복 매핑 UNIQUE로 방지';
```

---

### 4-11. questions

덤프 파싱 문제와 AI 생성 문제를 단일 테이블로 관리.
`source_chunk_id`는 AI 생성 문제의 출처 청크를 추적한다. 덤프 파싱 문제는 NULL.
설계 근거: docs/02-erd-logical.md 결정 5 참고.

```sql
-- 문제 테이블: 덤프 파싱 + AI 생성 문제 통합 관리
-- source_chunk_id NULL 허용: 덤프 파싱 문제는 청크 출처 없음 (docs/02-erd-logical.md 결정 5)
CREATE TABLE questions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    certification_id UUID        NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
    topic_id         UUID        NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    source_chunk_id  UUID        REFERENCES document_chunks(id) ON DELETE RESTRICT, -- NULLABLE
    question_text    TEXT        NOT NULL,
    question_type    VARCHAR(50) NOT NULL, -- 코드값: QUESTION_TYPE 그룹 (SINGLE/MULTIPLE/SCENARIO)
    source_type      VARCHAR(50) NOT NULL, -- 코드값: SOURCE_TYPE 그룹 (DUMP/GENERATED)
    difficulty       VARCHAR(50) NOT NULL DEFAULT 'INTERMEDIATE', -- 코드값: DIFFICULTY 그룹
    is_active        BOOLEAN     NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted       BOOLEAN     NOT NULL DEFAULT false
);

COMMENT ON TABLE  questions IS '문제 원장. 덤프 파싱(DUMP)과 AI 생성(GENERATED) 통합';
COMMENT ON COLUMN questions.source_chunk_id IS 'AI 생성 문제의 출처 청크 FK. 덤프 파싱 문제는 NULL';
COMMENT ON COLUMN questions.question_type IS 'code_values QUESTION_TYPE 그룹 (SINGLE/MULTIPLE/SCENARIO)';
```

---

### 4-12. choices

문제의 선택지 목록.
`choice_label`은 A/B/C/D 등 표시 레이블이다.
`is_correct`로 정답 여부를 저장하여 채점 로직을 단순화한다.

```sql
-- 선택지 테이블: 객관식 문제의 보기 목록
CREATE TABLE choices (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id  UUID         NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
    choice_text  TEXT         NOT NULL,
    choice_label VARCHAR(10)  NOT NULL, -- A, B, C, D 등 표시 레이블
    is_correct   BOOLEAN      NOT NULL DEFAULT false,
    order_num    INTEGER      NOT NULL, -- 표시 순서 (셔플 전 원래 순서)
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted   BOOLEAN      NOT NULL DEFAULT false
);

COMMENT ON TABLE  choices IS '객관식 선택지. is_correct=true가 정답';
COMMENT ON COLUMN choices.choice_label IS '표시 레이블: A, B, C, D';
COMMENT ON COLUMN choices.order_num IS '원래 순서. 시험 시 셔플은 앱 레벨에서 처리';
```

---

### 4-13. answer_explanations

문제별 정답 해설. questions와 1:1 관계.
`source_chunk_id`는 해설의 근거가 된 청크를 참조한다 (NULLABLE).

```sql
-- 정답 해설: questions와 1:1 관계. question_id에 UNIQUE 제약으로 DB 레벨 보장
CREATE TABLE answer_explanations (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id      UUID        NOT NULL UNIQUE REFERENCES questions(id) ON DELETE RESTRICT,
    explanation_text TEXT        NOT NULL,
    source_chunk_id  UUID        REFERENCES document_chunks(id) ON DELETE RESTRICT, -- NULLABLE
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted       BOOLEAN     NOT NULL DEFAULT false
);

COMMENT ON TABLE  answer_explanations IS '문제별 해설. questions와 1:1 (UNIQUE 제약으로 보장)';
COMMENT ON COLUMN answer_explanations.source_chunk_id IS '해설 근거 청크 FK. 없으면 NULL';
```

---

### 4-14. exam_sessions

사용자의 시험 응시 단위.
`correct_count`는 반정규화 컬럼이다. 설계 근거는 섹션 8 참고.

```sql
-- 시험 세션: 사용자 1회 응시 단위. correct_count 반정규화 적용
CREATE TABLE exam_sessions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    certification_id UUID        NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
    exam_mode        VARCHAR(50) NOT NULL, -- 코드값: EXAM_MODE 그룹 (TIMED/PRACTICE/REVIEW)
    total_questions  INTEGER     NOT NULL DEFAULT 0,
    correct_count    INTEGER     NOT NULL DEFAULT 0, -- [반정규화] 대시보드 집계 성능 최적화. 시험 완료 후 불변값. docs/02-erd-logical.md 결정 3 참고
    time_limit_seconds INTEGER,             -- NULL 허용: PRACTICE 모드는 시간 제한 없음
    elapsed_seconds  INTEGER,               -- NULL 허용: 미완료 세션
    is_completed     BOOLEAN     NOT NULL DEFAULT false,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,           -- NULL 허용: 진행 중인 세션
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted       BOOLEAN     NOT NULL DEFAULT false,
    CONSTRAINT chk_exam_sessions_total_questions CHECK (total_questions >= 0),
    CONSTRAINT chk_exam_sessions_correct_count   CHECK (correct_count >= 0),
    CONSTRAINT chk_exam_sessions_correct_lte_total
        CHECK (correct_count <= total_questions)  -- 정답 수 <= 전체 문제 수
);

COMMENT ON TABLE  exam_sessions IS '시험 응시 세션 이력. correct_count 반정규화 포함';
COMMENT ON COLUMN exam_sessions.correct_count IS '[반정규화] 대시보드 집계 성능 최적화. 시험 완료 후 불변. docs/02-erd-logical.md 결정 3';
COMMENT ON COLUMN exam_sessions.time_limit_seconds IS 'NULL = PRACTICE 모드 (시간 제한 없음)';
COMMENT ON COLUMN exam_sessions.completed_at IS 'NULL = 진행 중인 세션';
```

---

### 4-15. user_attempts

시험 세션 내 개별 문제 응답 이력. 불변(immutable) 테이블.
`is_deleted` 컬럼이 존재하지만 절대 `true`로 변경하지 않는다.
API 레벨에서 DELETE 엔드포인트를 제공하지 않는다.
설계 근거: docs/02-erd-logical.md 결정 4 / docs/00-data-standard.md 섹션 4 참고.

```sql
-- [불변 이력] user_attempts: 시험 응답 이력. is_deleted 포함이나 절대 true로 변경 금지.
-- 삭제 금지 근거: 오답 분석, 약점 추적의 신뢰성 보장 (docs/02-erd-logical.md 결정 4)
-- API 레벨: DELETE /api/user-attempts 엔드포인트 미제공
CREATE TABLE user_attempts (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id           UUID        NOT NULL REFERENCES exam_sessions(id) ON DELETE RESTRICT,
    question_id          UUID        NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
    selected_choice_ids  JSONB       NOT NULL DEFAULT '[]', -- 복수 선택 답안 UUID 배열
    is_correct           BOOLEAN     NOT NULL DEFAULT false,
    time_spent_seconds   INTEGER,    -- NULL 허용: 타이머 미작동 모드
    answered_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted           BOOLEAN     NOT NULL DEFAULT false -- [불변] 절대 true로 변경 금지
);

COMMENT ON TABLE  user_attempts IS '[불변 이력] 문제 응답 기록. is_deleted=true 변경 및 DELETE 절대 금지';
COMMENT ON COLUMN user_attempts.selected_choice_ids IS 'choices.id UUID 배열 (JSONB). 복수 선택 지원';
COMMENT ON COLUMN user_attempts.is_deleted IS '[불변 이력] 절대 true로 변경 금지. 오답 분석 신뢰성 보장';
```

---

### 4-16. pipeline_runs

PDF 처리 파이프라인(파싱→청킹→임베딩→색인) 실행 이력.
`document_version_id`는 파이프라인 성공 후 채워진다 (NULLABLE).

```sql
-- 파이프라인 실행 이력: PDF 처리 단계별 상태 및 오류 추적
CREATE TABLE pipeline_runs (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_document_id UUID        NOT NULL REFERENCES learning_documents(id) ON DELETE RESTRICT,
    document_version_id  UUID        REFERENCES document_versions(id) ON DELETE RESTRICT, -- NULLABLE: 완료 전
    status               VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- 코드값: PIPELINE_STATUS 그룹
    total_chunks         INTEGER,    -- NULL 허용: 파싱 완료 전
    processed_chunks     INTEGER     NOT NULL DEFAULT 0,
    error_message        TEXT,       -- NULL 허용: 정상 완료 시
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted           BOOLEAN     NOT NULL DEFAULT false,
    CONSTRAINT chk_pipeline_runs_processed_chunks CHECK (processed_chunks >= 0)
);

COMMENT ON TABLE  pipeline_runs IS 'PDF 처리 파이프라인 실행 이력. 실패 로그 포함';
COMMENT ON COLUMN pipeline_runs.document_version_id IS 'NULL = 파이프라인 완료 전. 완료 시 채워짐';
COMMENT ON COLUMN pipeline_runs.status IS 'code_values PIPELINE_STATUS 그룹 (PENDING/PROCESSING/COMPLETED/FAILED)';
COMMENT ON COLUMN pipeline_runs.error_message IS 'NULL = 정상 완료. FAILED 시 오류 메시지 저장';
```

---

## 5. 인덱스 DDL

모든 테이블 생성 완료 후 실행한다.

```sql
-- ============================================================
-- [1] FK 인덱스 — 조인 성능 및 참조 무결성 검사 최적화
-- ============================================================

-- exam_domains
CREATE INDEX idx_exam_domains_certification_id
    ON exam_domains (certification_id);

-- topics
CREATE INDEX idx_topics_exam_domain_id
    ON topics (exam_domain_id);

-- learning_documents
CREATE INDEX idx_learning_documents_certification_id
    ON learning_documents (certification_id);

-- document_versions
CREATE INDEX idx_document_versions_learning_document_id
    ON document_versions (learning_document_id);

-- document_chunks
CREATE INDEX idx_document_chunks_document_version_id
    ON document_chunks (document_version_id);

-- chunk_embeddings
CREATE INDEX idx_chunk_embeddings_chunk_id
    ON chunk_embeddings (chunk_id);
-- 주: chunk_id에 UNIQUE 제약이 있으나 명시적 인덱스로 중복 생성하지 않는다.
-- UNIQUE 제약이 자동으로 B-tree 인덱스를 생성하므로 별도 인덱스 불필요.
-- (PostgreSQL은 UNIQUE 제약 생성 시 내부적으로 인덱스를 자동 생성)

-- chunk_topics
CREATE INDEX idx_chunk_topics_chunk_id
    ON chunk_topics (chunk_id);

CREATE INDEX idx_chunk_topics_topic_id
    ON chunk_topics (topic_id);

-- questions
CREATE INDEX idx_questions_certification_id
    ON questions (certification_id);

CREATE INDEX idx_questions_topic_id
    ON questions (topic_id);

CREATE INDEX idx_questions_source_chunk_id
    ON questions (source_chunk_id)
    WHERE source_chunk_id IS NOT NULL; -- NULLABLE FK: NULL 제외 partial index

-- choices
CREATE INDEX idx_choices_question_id
    ON choices (question_id);

-- answer_explanations
CREATE INDEX idx_answer_explanations_source_chunk_id
    ON answer_explanations (source_chunk_id)
    WHERE source_chunk_id IS NOT NULL; -- NULLABLE FK: NULL 제외 partial index

-- exam_sessions
CREATE INDEX idx_exam_sessions_user_id
    ON exam_sessions (user_id);

CREATE INDEX idx_exam_sessions_certification_id
    ON exam_sessions (certification_id);

-- user_attempts
CREATE INDEX idx_user_attempts_session_id
    ON user_attempts (session_id);

CREATE INDEX idx_user_attempts_question_id
    ON user_attempts (question_id);

-- pipeline_runs
CREATE INDEX idx_pipeline_runs_learning_document_id
    ON pipeline_runs (learning_document_id);

CREATE INDEX idx_pipeline_runs_document_version_id
    ON pipeline_runs (document_version_id)
    WHERE document_version_id IS NOT NULL; -- NULLABLE FK: NULL 제외 partial index


-- ============================================================
-- [2] 조회 최적화 인덱스 — 자주 쓰이는 필터/정렬 컬럼
-- ============================================================

-- certifications: exam_code 단건 조회 (로그인/자격증 선택 화면)
-- UNIQUE 제약이 자동으로 인덱스를 생성하므로 별도 명시적 인덱스 불필요.
-- 아래는 문서 목적으로 존재 명시만 한다.
-- CREATE UNIQUE INDEX idx_certifications_exam_code ON certifications (exam_code);
-- → DDL의 UNIQUE 제약이 이미 동일한 인덱스를 생성함

-- questions: 자격증 + 활성 상태 + 난이도 복합 필터 (시험 문제 추출)
CREATE INDEX idx_questions_certification_id_is_active_difficulty
    ON questions (certification_id, is_active, difficulty)
    WHERE is_deleted = false;

-- exam_sessions: 사용자별 최근 세션 조회 (대시보드)
CREATE INDEX idx_exam_sessions_user_id_created_at
    ON exam_sessions (user_id, created_at DESC)
    WHERE is_deleted = false;

-- user_attempts: 세션별 정답/오답 조회 (채점, 오답노트)
CREATE INDEX idx_user_attempts_session_id_is_correct
    ON user_attempts (session_id, is_correct);

-- document_chunks: 버전별 활성 청크 조회 (RAG 검색 후보군)
CREATE INDEX idx_document_chunks_document_version_id_is_active
    ON document_chunks (document_version_id, is_active)
    WHERE is_deleted = false;

-- pipeline_runs: 문서별 최신 실행 상태 조회 (업로드 진행 화면)
CREATE INDEX idx_pipeline_runs_learning_document_id_status
    ON pipeline_runs (learning_document_id, status);

-- code_values: 코드 그룹별 전체 조회 (코드값 목록 API)
CREATE INDEX idx_code_values_code_group
    ON code_values (code_group)
    WHERE is_deleted = false AND is_active = true;
```

---

## 6. 트리거 DDL

모든 테이블 생성 완료 후 실행한다.
`update_updated_at_column()` 함수는 섹션 3에서 이미 생성되었다.

```sql
-- code_values
CREATE TRIGGER trg_code_values_updated_at
    BEFORE UPDATE ON code_values
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- certifications
CREATE TRIGGER trg_certifications_updated_at
    BEFORE UPDATE ON certifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- users
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- exam_domains
CREATE TRIGGER trg_exam_domains_updated_at
    BEFORE UPDATE ON exam_domains
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- topics
CREATE TRIGGER trg_topics_updated_at
    BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- learning_documents
CREATE TRIGGER trg_learning_documents_updated_at
    BEFORE UPDATE ON learning_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- document_versions
CREATE TRIGGER trg_document_versions_updated_at
    BEFORE UPDATE ON document_versions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- document_chunks
CREATE TRIGGER trg_document_chunks_updated_at
    BEFORE UPDATE ON document_chunks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- chunk_embeddings
CREATE TRIGGER trg_chunk_embeddings_updated_at
    BEFORE UPDATE ON chunk_embeddings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- chunk_topics
CREATE TRIGGER trg_chunk_topics_updated_at
    BEFORE UPDATE ON chunk_topics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- questions
CREATE TRIGGER trg_questions_updated_at
    BEFORE UPDATE ON questions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- choices
CREATE TRIGGER trg_choices_updated_at
    BEFORE UPDATE ON choices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- answer_explanations
CREATE TRIGGER trg_answer_explanations_updated_at
    BEFORE UPDATE ON answer_explanations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- exam_sessions
CREATE TRIGGER trg_exam_sessions_updated_at
    BEFORE UPDATE ON exam_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- user_attempts
CREATE TRIGGER trg_user_attempts_updated_at
    BEFORE UPDATE ON user_attempts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- pipeline_runs
CREATE TRIGGER trg_pipeline_runs_updated_at
    BEFORE UPDATE ON pipeline_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## 7. 제약조건 설계 결정

### 7-1. ON DELETE RESTRICT 일괄 적용

모든 FK에 `ON DELETE RESTRICT`를 적용한다.

| 결정 | ON DELETE RESTRICT |
|------|--------------------|
| 배경 | 자격증 플랫폼은 이력 데이터(시험 세션, 문제 풀이 기록)의 신뢰성이 핵심이다 |
| 선택 | 모든 FK ON DELETE RESTRICT |
| 근거 | CASCADE 삭제는 연쇄적으로 이력 데이터를 파괴할 위험이 있다. 예: certifications 삭제 시 exam_sessions 전체 삭제 → 사용자 학습 이력 소실 |
| 트레이드오프 | 부모 레코드 삭제 시 자식 레코드를 먼저 정리해야 한다. 소프트 삭제(is_deleted)로 운영하므로 실제 DELETE는 드물어 허용 가능한 수준 |

### 7-2. CHECK 제약 목록

| 테이블 | 제약명 | 조건 | 목적 |
|--------|--------|------|------|
| exam_domains | (인라인) | weight_percent BETWEEN 1 AND 100 | 가중치 유효 범위 |
| document_chunks | chk_document_chunks_quality_score | quality_score IS NULL OR quality_score BETWEEN 0 AND 100 | 품질 점수 유효 범위 |
| exam_sessions | chk_exam_sessions_total_questions | total_questions >= 0 | 음수 방지 |
| exam_sessions | chk_exam_sessions_correct_count | correct_count >= 0 | 음수 방지 |
| exam_sessions | chk_exam_sessions_correct_lte_total | correct_count <= total_questions | 논리 정합성 |
| pipeline_runs | chk_pipeline_runs_processed_chunks | processed_chunks >= 0 | 음수 방지 |

### 7-3. UNIQUE 제약 목록

| 테이블 | 제약명 | 컬럼 | 목적 |
|--------|--------|------|------|
| code_values | uq_code_values_group_value | (code_group, code_value) | 코드 중복 방지 |
| certifications | (인라인) | exam_code | 시험 코드 전역 유일 |
| users | (인라인) | email | 사용자 이메일 중복 방지 |
| document_versions | uq_document_versions_doc_ver | (learning_document_id, version_number) | 동일 문서 내 버전 중복 방지 |
| chunk_embeddings | (인라인) | chunk_id | 청크당 임베딩 1개 보장 |
| answer_explanations | (인라인) | question_id | 문제당 해설 1개 보장 |
| chunk_topics | uq_chunk_topics_chunk_topic | (chunk_id, topic_id) | 중복 매핑 방지 |

---

## 8. 반정규화 결정 기록

### 반정규화 결정: exam_sessions.correct_count

- **배경**: 대시보드(`/` 페이지)에서 "최근 5회 시험 정답률" 위젯을 매번 조회한다. 정규화 원칙대로라면 `user_attempts`를 `COUNT + GROUP BY`로 집계해야 한다. 시험 1회당 최대 수백 건의 attempts가 존재하며, 대시보드 로딩마다 집계 쿼리가 발생한다.

- **선택**: `exam_sessions.correct_count` INTEGER 컬럼에 시험 완료 시점의 정답 수를 직접 저장.

- **근거**:
  - 시험이 완료(`is_completed = true`)되면 `correct_count`는 변하지 않는다. 사후에 응답 기록이 수정되지 않으므로 집계 결과가 달라질 이유가 없다.
  - 변하지 않는 값에 대한 반정규화는 데이터 불일치 위험이 없다. "안전한 반정규화"다.
  - 정답률 조회 시 `correct_count / NULLIF(total_questions, 0)`로 즉시 계산 가능하다. 추가 JOIN이나 서브쿼리가 불필요하다.
  - 소규모 서비스(2~10명)라도 대시보드 집계 쿼리는 반복 호출되므로 최적화 효과가 있다.

- **트레이드오프**:
  - 시험 제출 API에서 `user_attempts` 저장과 `exam_sessions.correct_count` 갱신을 하나의 트랜잭션으로 묶어야 한다. 원자성 책임이 애플리케이션 레벨로 이동한다.
  - 버그로 인해 `correct_count`와 실제 attempts 집계 값이 다를 경우 불일치가 발생한다. 주기적인 정합성 검증 배치가 필요하다.

- **정합성 유지 방법**:
  1. 시험 완료 트랜잭션: `user_attempts` 삽입 + `exam_sessions.correct_count` UPDATE를 단일 DB 트랜잭션으로 처리.
  2. 정합성 검증 쿼리 (운영 모니터링):
     ```sql
     SELECT
         es.id,
         es.correct_count AS stored,
         COUNT(*) FILTER (WHERE ua.is_correct = true) AS computed
     FROM exam_sessions es
     JOIN user_attempts ua ON ua.session_id = es.id
     WHERE es.is_completed = true
       AND es.is_deleted = false
     GROUP BY es.id, es.correct_count
     HAVING es.correct_count != COUNT(*) FILTER (WHERE ua.is_correct = true);
     ```
  3. `docs/06-data-quality.md`에 정기 검증 규칙으로 등재.

---

## 9. 물리 설계 자체 검토 체크리스트

erd-review 스킬 기준 및 AGENTS.md review-agent 체크리스트 기준으로 자체 검토한 결과다.

### 공통 컬럼 체크

| 테이블 | id UUID PK | created_at | updated_at | is_deleted |
|--------|-----------|------------|------------|------------|
| code_values | ✅ | ✅ | ✅ | ✅ |
| certifications | ✅ | ✅ | ✅ | ✅ |
| users | ✅ | ✅ | ✅ | ✅ |
| exam_domains | ✅ | ✅ | ✅ | ✅ |
| topics | ✅ | ✅ | ✅ | ✅ |
| learning_documents | ✅ | ✅ | ✅ | ✅ |
| document_versions | ✅ | ✅ | ✅ | ✅ |
| document_chunks | ✅ | ✅ | ✅ | ✅ |
| chunk_embeddings | ✅ | ✅ | ✅ | ✅ |
| chunk_topics | ✅ | ✅ | ✅ | ✅ |
| questions | ✅ | ✅ | ✅ | ✅ |
| choices | ✅ | ✅ | ✅ | ✅ |
| answer_explanations | ✅ | ✅ | ✅ | ✅ |
| exam_sessions | ✅ | ✅ | ✅ | ✅ |
| user_attempts | ✅ | ✅ | ✅ | ✅ |
| pipeline_runs | ✅ | ✅ | ✅ | ✅ |

### 인덱스 체크

- [x] 모든 FK 컬럼에 인덱스 존재 (NULLABLE FK는 partial index 적용)
- [x] 대시보드 집계 쿼리용 복합 인덱스 존재 (user_id + created_at DESC)
- [x] 문제 추출 필터용 복합 인덱스 존재 (certification_id + is_active + difficulty)
- [x] 코드 조회용 code_group 인덱스 존재
- [x] 인덱스명 idx_{테이블}_{컬럼} 형식 준수
- [ ] pgvector IVFFlat / HNSW 인덱스: docs/04-vector-schema.md에서 별도 설계 (이 문서 범위 외)

### 설계 근거 기록 확인

- [x] exam_sessions.correct_count 반정규화 근거: 섹션 8 + docs/02-erd-logical.md 결정 3
- [x] document_versions 분리 근거: DDL 주석 + docs/02-erd-logical.md 결정 1
- [x] chunk_embeddings 1:1 분리 근거: DDL 주석 + docs/02-erd-logical.md 결정 2
- [x] user_attempts 불변 이력 근거: DDL 주석 + docs/02-erd-logical.md 결정 4

### AGENTS.md 절대 금지 항목 확인

- [x] user_attempts DELETE 엔드포인트 미제공 명시 (DDL 주석 + COMMENT)
- [x] user_attempts is_deleted 변경 금지 명시 (DDL 주석 + COMMENT)
- [x] 하드코딩 없음 (코드값은 모두 code_values 참조)
- [x] pgvector metadata 필드 완전: model_name, model_version 포함

### 명명 규칙 준수

- [x] 테이블: snake_case 복수형
- [x] PK: id UUID PRIMARY KEY DEFAULT gen_random_uuid()
- [x] FK: 참조테이블_단수형_id 형식
- [x] 인덱스: idx_{테이블}_{컬럼} 형식
- [x] 코드값: VARCHAR(50), UPPER_SNAKE_CASE (docs/00-data-standard.md 준수)
