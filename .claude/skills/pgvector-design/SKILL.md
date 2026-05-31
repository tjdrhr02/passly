---
name: pgvector-design
description: pgvector 스키마를 설계하거나 RAG 검색을 구현할 때 사용. docs/04-vector-schema.md 작성 시, chunk_embeddings 테이블 설계 시, pre-vector-index Hook 트리거 시 호출.
version: 1.0.0
---

# Skill: pgvector 설계

## 사용 시점
- docs/04-vector-schema.md 작성 시
- chunk_embeddings 테이블 설계 시
- RAG 검색 구현 시
- pre-vector-index Hook이 이 파일을 지정했을 때

---

## pgvector 기본 설계 원칙

### 1. 벡터 컬럼 정의
```sql
-- chunk_embeddings 테이블
embedding vector(768)  -- Gemini embedding-001 차원수
```

### 2. 필수 metadata 필드
벡터만 저장하면 검색 품질 관리가 불가능하다.
아래 metadata를 반드시 함께 설계한다:

| 필드 | 목적 |
|------|------|
| chunk_id | document_chunks FK — 원문 조회 |
| certification_id | 자격증 필터링 |
| exam_domain_id | 시험 영역 필터링 |
| topic_id | 학습 개념 필터링 |
| difficulty | 난이도 필터링 |
| access_level | 권한 기반 검색 제한 |
| quality_score | 품질 낮은 청크 제외 |
| is_active | 비활성 청크 제외 |
| model_name | 임베딩 모델 추적 |
| model_version | 모델 버전 추적 |

### 3. 인덱스 전략
```sql
-- IVFFlat (빠른 근사 검색, 소규모 데이터에 적합)
CREATE INDEX idx_chunk_embeddings_vector
ON chunk_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 선택 기준:
-- 청크 수 < 10만 → IVFFlat (lists = sqrt(row_count))
-- 청크 수 > 10만 → HNSW 고려
```

### 4. Hybrid Search 구조
Vector search 단독으로는 정확한 기술 용어 검색에 약하다.
Full-text search와 결합한 hybrid 구조를 설계한다.

```sql
-- document_chunks에 full-text search 컬럼 추가
ALTER TABLE document_chunks
ADD COLUMN chunk_tsv tsvector
GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED;

CREATE INDEX idx_chunks_tsv ON document_chunks USING gin(chunk_tsv);
```

검색 흐름:
```
질문 입력
  → Vector Search (의미 기반) → Top-K 결과
  → Full-text Search (키워드 기반) → Top-K 결과
  → RRF (Reciprocal Rank Fusion) 통합
  → 최종 Top-K 반환
```

### 5. 검색 쿼리 패턴
```python
# Vector search
SELECT c.*, ce.embedding <=> $1::vector AS distance
FROM document_chunks c
JOIN chunk_embeddings ce ON c.id = ce.chunk_id
WHERE c.certification_id = $2
  AND c.is_active = true
  AND c.quality_score >= 60
ORDER BY distance
LIMIT 10;
```

---

## 품질 기준
- [ ] 벡터 차원수가 사용 모델과 일치하는가? (Gemini: 768)
- [ ] metadata 필드가 모두 포함되어 있는가?
- [ ] 인덱스 선택 근거가 docs/04-vector-schema.md에 있는가?
- [ ] Hybrid Search 구조가 설계되어 있는가?
