---
name: search-eval
description: 검색 품질을 평가하거나 docs/07-search-evaluation.md를 작성할 때 사용. Wave 5 검색 품질 평가 단계에서 호출.
version: 1.0.0
---

# Skill: 검색 품질 평가

## 사용 시점
- docs/07-search-evaluation.md 작성 시
- Wave 5 검색 품질 평가 단계에서

---

## 평가 지표

### Recall@K
상위 K개 결과 안에 정답 청크가 포함된 비율.
```
Recall@K = (정답 포함된 쿼리 수) / (전체 쿼리 수)
K = 3, 5, 10으로 각각 측정
```

### MRR (Mean Reciprocal Rank)
정답이 몇 번째에 있는지의 역수 평균.
```
MRR = (1/N) × Σ(1 / rank_i)
높을수록 정답이 상위에 위치
```

### 응답 레이턴시
```
P50, P95, P99 레이턴시 측정
목표: P95 < 2초
```

---

## 비교 평가 구조

세 가지 검색 방식을 동일 쿼리셋으로 비교한다:

| 방식 | 설명 |
|------|------|
| Keyword Search | PostgreSQL Full-text (tsvector) |
| Vector Search | pgvector cosine similarity |
| Hybrid Search | RRF (Reciprocal Rank Fusion) 통합 |

### 평가 쿼리셋 구성
- 기술 용어 정확 검색 (예: "Azure OpenAI Service")
- 의미 기반 검색 (예: "자연어로 텍스트 생성하는 서비스")
- 복합 시나리오 검색 (예: "비용 효율적인 텍스트 요약 방법")

---

## 결과 문서 형식
```markdown
## 검색 품질 평가 결과

### 평가 환경
- 청크 수: N개
- 쿼리 수: N개
- 평가일: YYYY-MM-DD

### 지표 비교
| 방식 | Recall@3 | Recall@5 | MRR | P95 레이턴시 |
|------|---------|---------|-----|------------|
| Keyword | | | | |
| Vector | | | | |
| Hybrid | | | | |

### 분석
- 기술 용어 검색: [어떤 방식이 유리했는가]
- 의미 기반 검색: [어떤 방식이 유리했는가]
- 최종 선택: Hybrid Search (이유: ...)
```
