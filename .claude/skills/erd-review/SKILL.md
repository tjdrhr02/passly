---
name: erd-review
description: ERD를 작성하거나 검토할 때 사용. docs/02-erd-logical.md 또는 docs/03-erd-physical.md 작성 시, pre-db-change Hook 트리거 시 호출.
version: 1.0.0
---

# Skill: ERD 검토

## 사용 시점
- docs/02-erd-logical.md 작성/검토 시
- docs/03-erd-physical.md 작성/검토 시
- pre-db-change Hook이 이 파일을 지정했을 때

---

## 논리 ERD 검토 기준

### 정규화 체크
- [ ] 1NF: 하나의 컬럼에 하나의 값만 있는가?
- [ ] 2NF: 복합 PK라면 모든 컬럼이 PK 전체에 종속되는가?
- [ ] 3NF: 이행 종속이 없는가? (A→B→C 구조 금지)
- [ ] 반정규화 적용 시 근거가 docs/02-erd-logical.md에 기록되어 있는가?

### 엔터티 체크
- [ ] 모든 엔터티가 docs/00-data-standard.md 표준 용어 사전과 일치하는가?
- [ ] M:N 관계는 교차 테이블로 분해되었는가?
- [ ] 이력 추적이 필요한 엔터티에 이력 테이블이 있는가?

### Passly 필수 엔터티 포함 여부
- [ ] certifications
- [ ] exam_domains
- [ ] topics
- [ ] learning_documents
- [ ] document_versions (이력)
- [ ] document_chunks
- [ ] chunk_embeddings (pgvector)
- [ ] questions
- [ ] choices
- [ ] answer_explanations
- [ ] users
- [ ] exam_sessions (이력, correct_count 반정규화 포함)
- [ ] user_attempts (불변 이력)
- [ ] pipeline_runs (이력)
- [ ] code_values (코드 테이블)

---

## 물리 ERD / DDL 검토 기준

### 공통 컬럼 체크
```sql
-- 모든 테이블에 아래 4개 필수
id          UUID        PRIMARY KEY DEFAULT gen_random_uuid()
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
is_deleted  BOOLEAN     NOT NULL DEFAULT false
```

### 인덱스 체크
- [ ] FK 컬럼에 인덱스가 있는가?
- [ ] 자주 조회하는 필터 컬럼에 인덱스가 있는가?
- [ ] 인덱스명이 idx_테이블_컬럼 형식인가?
- [ ] pgvector 컬럼에 IVFFlat 또는 HNSW 인덱스가 있는가?

### 설계 근거 기록 확인
아래 항목은 docs/02-erd-logical.md에 반드시 근거가 있어야 한다:
- exam_sessions.correct_count 반정규화 이유
- document_versions 분리 이유
- chunk_embeddings 1:1 분리 이유
- user_attempts 불변 이력 설계 이유
