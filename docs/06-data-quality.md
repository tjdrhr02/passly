# Passly 데이터 품질 규칙 및 거버넌스 정책

> 버전: 1.0 | 작성일: 2026-05
> DA 거버넌스 영역 핵심 산출물. Wave 1 설계 단계 최종 문서.
> 참조 문서: docs/00-data-standard.md, docs/03-erd-physical.md, docs/04-vector-schema.md, docs/05-rag-pipeline.md

---

## 목차

1. [quality_score 계산 기준](#1-quality_score-계산-기준)
2. [파싱 실패율 관리](#2-파싱-실패율-관리)
3. [중복 청크 감지 기준](#3-중복-청크-감지-기준)
4. [거버넌스 정책](#4-거버넌스-정책)
   - 4-1. 출처(Lineage) 추적
   - 4-2. 버전 관리 정책
   - 4-3. 접근 권한(Access Control) 정책
5. [품질 검증 쿼리 예시](#5-품질-검증-쿼리-예시)
6. [정기 검증 스케줄](#6-정기-검증-스케줄)
7. [절대 금지 사항](#7-절대-금지-사항)

---

## 1. quality_score 계산 기준

### 1-1. 설계 결정

| 항목 | 내용 |
|------|------|
| 배경 | RAG 검색 품질은 청크 단위 텍스트 품질에 직결된다. 토큰 수가 너무 적으면 맥락이 부족하고, 인코딩 깨짐이 있으면 LLM이 오해석한다. 품질 미달 청크를 검색 대상에서 제외하면 hallucination 발생 가능성이 줄어든다. |
| 선택 | 5개 지표를 가중합산하는 0~100 점수로 청크 품질을 정량화하고, 등급 기준에 따라 is_active 처리. |
| 근거 | 단일 지표(예: 토큰 수 필터만)는 인코딩 깨짐 청크를 걸러내지 못한다. 다차원 지표는 실질적인 검색 유해 청크를 더 정밀하게 제거한다. |
| 트레이드오프 | 파이프라인 처리 시간이 증가한다. Gemini API 호출 전 CPU 기반 사전 필터링이므로 추가 비용은 없으며, 처리 지연은 수 밀리초 수준으로 허용 가능하다. |

### 1-2. 5개 지표 배점 상세

| 지표명 | 배점 | 측정 대상 | 경계값 및 산출 방법 |
|--------|------|----------|-------------------|
| 토큰 수 적정성 | 30점 | `token_count` | 300~500 토큰: 30점 / 100~299 또는 501~700: 15점 / 그 외: 0점 |
| 텍스트 다양성 | 25점 | `chunk_text` 문자 다양성 | `unique_chars / total_chars` 비율 계산 → 비율 x 25점 (최대 25점). 비율 0.3 미만은 0점 처리 |
| 구조 완결성 | 20점 | `chunk_text` 문장 완결도 | 마침표/물음표로 끝나는 문장 비율 계산 → 비율 x 20점 (최대 20점) |
| 인코딩 안정성 | 15점 | `chunk_text` 내 U+FFFD (replacement character) 비율 | U+FFFD 없음: 15점 / U+FFFD 비율 1% 미만: 8점 / 1% 이상: 0점 |
| 섹션 경로 존재 | 10점 | 섹션 제목 메타데이터 유무 | 섹션 제목 메타데이터 있음: 10점 / 없음: 0점 |

**합계: 최대 100점**

### 1-3. 등급 기준 및 처리 방침

| 등급 | 점수 범위 | 처리 방침 | is_active |
|------|----------|----------|-----------|
| 정상 | 80~100점 | 검색 대상 포함, 정상 운영 | true |
| 경고 | 60~79점 | 검색 대상 포함, 품질 개선 검토 대상으로 마킹 | true |
| 불량 | 60점 미만 | 검색 대상 제외, 자동 비활성화 | false |

- **경고 등급(60~79점)**: 즉시 비활성화하지 않는다. 소규모 서비스 특성상 청크 수가 적으면 검색 품질 저하가 더 심각하다. 대신 운영 모니터링 대상으로 분류하여 다음 문서 재업로드 주기에 개선을 유도한다.
- **불량 등급(60점 미만)**: 파이프라인 완료 시점에 `is_active = false`로 자동 처리한다. 검색 쿼리는 `WHERE is_active = true` 조건으로 자동 제외된다.

### 1-4. quality_score NULL 처리 정책

- `quality_score IS NULL`은 파이프라인이 아직 품질 평가 단계에 도달하지 못한 상태를 의미한다.
- NULL 청크는 검색 대상에서 제외한다. 검색 쿼리 필터: `WHERE quality_score IS NOT NULL AND (quality_score >= 60 OR quality_score IS NOT NULL)` 대신 명시적으로 `WHERE is_active = true AND quality_score IS NOT NULL`.
- 단, NULL이면서 `is_active = true`인 청크가 존재한다면 파이프라인 미완료 상태이므로 쿼리 #3으로 감지한다.

### 1-5. Python 계산 예시

```python
import re
from dataclasses import dataclass


@dataclass
class ChunkQualityInput:
    chunk_text: str
    token_count: int
    section_title: str | None  # 섹션 제목 메타데이터


def compute_quality_score(chunk: ChunkQualityInput) -> float:
    """
    5개 지표를 합산하여 quality_score (0.00~100.00) 산출.
    반환값은 document_chunks.quality_score 컬럼에 저장된다.
    """
    score = 0.0

    # [1] 토큰 수 적정성 (30점)
    t = chunk.token_count
    if 300 <= t <= 500:
        score += 30
    elif (100 <= t <= 299) or (501 <= t <= 700):
        score += 15
    # else: 0점

    # [2] 텍스트 다양성 (25점)
    text = chunk.chunk_text
    if len(text) > 0:
        unique_ratio = len(set(text)) / len(text)
        if unique_ratio >= 0.3:
            score += min(unique_ratio * 25, 25.0)
    # 0 길이 또는 비율 0.3 미만: 0점

    # [3] 구조 완결성 (20점)
    sentences = re.split(r'(?<=[.?!])\s', text)
    if sentences:
        complete = sum(1 for s in sentences if s.strip().endswith(('.', '?')))
        completeness_ratio = complete / len(sentences)
        score += min(completeness_ratio * 20, 20.0)

    # [4] 인코딩 안정성 (15점)
    replacement_count = text.count('�')
    if replacement_count == 0:
        score += 15
    elif len(text) > 0 and replacement_count / len(text) < 0.01:
        score += 8
    # else: 0점

    # [5] 섹션 경로 존재 (10점)
    if chunk.section_title:
        score += 10

    return round(score, 2)


def resolve_is_active(quality_score: float) -> bool:
    """60점 미만이면 검색 대상에서 제외."""
    return quality_score >= 60.0
```

---

## 2. 파싱 실패율 관리

### 2-1. 설계 결정

| 항목 | 내용 |
|------|------|
| 배경 | PDF 파싱은 파일 구조, 인코딩, 보안 잠금 등 다양한 이유로 실패할 수 있다. 실패율이 높으면 지식 베이스 완전성이 훼손된다. |
| 선택 | `pipeline_runs.status` 컬럼 기반으로 실패율을 추적하고, FAILED 비율 20% 초과 시 알림 대상으로 분류한다. |
| 근거 | 20% 임계값은 5건 중 1건 이상 실패하는 상황이다. 소규모 서비스에서 이 수준이면 실질적인 지식 베이스 훼손으로 이어진다. |
| 트레이드오프 | 임계값을 낮추면 오탐(false positive) 알림이 잦아진다. 20%는 보수적이나 소규모 서비스 현실을 반영한 균형점이다. |

### 2-2. 파싱 실패 원인 분류

| 원인 분류 | error_message 패턴 | 재처리 가능 여부 |
|---------|-------------------|----------------|
| 인코딩 오류 | `UnicodeDecodeError`, `invalid byte sequence` | 가능 (파일 재인코딩 후 재시도) |
| 구조 인식 실패 | `no text layer found`, `fitz error` | 조건부 (OCR 처리 후 재시도 검토) |
| 빈 페이지/문서 | `empty document`, `no pages extracted` | 불가 (원본 파일 문제) |
| 파일 접근 실패 | `FileNotFoundError`, `permission denied` | 가능 (파일 재업로드 후 재시도) |
| 보안 잠금 | `PDF encrypted`, `password required` | 불가 (원본 파일 문제) |

### 2-3. 파싱 성공률 모니터링 SQL

```sql
-- 목적: 문서별 파이프라인 실행 성공/실패 현황 조회
-- 실행 주기: 파이프라인 실행마다 (쿼리 #4와 동일)
SELECT
    ld.id                                           AS document_id,
    ld.title                                        AS document_title,
    COUNT(*)                                        AS total_runs,
    COUNT(*) FILTER (WHERE pr.status = 'COMPLETED') AS success_count,
    COUNT(*) FILTER (WHERE pr.status = 'FAILED')    AS fail_count,
    ROUND(
        COUNT(*) FILTER (WHERE pr.status = 'FAILED') * 100.0 / NULLIF(COUNT(*), 0),
        2
    )                                               AS fail_rate_pct
FROM learning_documents ld
LEFT JOIN pipeline_runs pr ON pr.learning_document_id = ld.id
    AND pr.is_deleted = false
WHERE ld.is_deleted = false
GROUP BY ld.id, ld.title
ORDER BY fail_rate_pct DESC NULLS LAST;
```

### 2-4. 실패 문서 재처리 정책

1. `pipeline_runs.status = 'FAILED'` 확인 후 `error_message` 원인 분류
2. 재처리 가능한 원인이면 원본 파일 보정 후 `/upload` 재업로드
3. 재업로드 시 `document_versions`에 신규 버전 생성 (기존 버전 is_active=false 처리)
4. 신규 `pipeline_runs` 레코드 생성 후 파이프라인 재실행
5. 이전 실패 `pipeline_runs` 레코드는 삭제하지 않고 이력으로 보존

---

## 3. 중복 청크 감지 기준

### 3-1. 설계 결정

| 항목 | 내용 |
|------|------|
| 배경 | PDF 재업로드, overlap 청킹 설정, 동일 내용의 여러 문서 업로드 시 동일하거나 유사한 청크가 중복 생성될 수 있다. 중복 청크는 RAG 검색 결과에 동일한 내용이 반복되어 LLM 컨텍스트를 낭비한다. |
| 선택 | (1) MD5 해시 기반 exact duplicate 감지, (2) 코사인 유사도 0.98 초과 near-duplicate 감지의 두 단계 전략. |
| 근거 | Exact duplicate는 해시 비교로 O(n) 처리 가능하다. Near-duplicate는 벡터 유사도를 활용하며 0.98은 경험적으로 의미 동일성이 높은 임계값이다. |
| 트레이드오프 | Near-duplicate 감지는 전체 벡터 쌍 비교가 필요하므로 청크 수 증가에 따라 비용이 증가한다. 소규모 서비스(1만~3만 청크) 범위에서는 파이프라인 완료 직후 1회 실행으로 충분하다. |

### 3-2. 중복 정의

| 중복 유형 | 정의 | 감지 방법 |
|---------|------|---------|
| 동일 문서 내 exact duplicate | 동일 `document_version_id` 내 `chunk_text`가 완전히 동일 | MD5(chunk_text) 해시 비교 |
| 다른 문서 간 exact duplicate | 다른 `document_version_id`에서 `chunk_text`가 완전히 동일 | MD5(chunk_text) 해시 비교 |
| near-duplicate | 어떤 문서에서든 코사인 유사도 > 0.98인 청크 쌍 | 벡터 유사도 비교 |

### 3-3. 중복 발생 원인

| 발생 원인 | 설명 |
|---------|------|
| PDF 중복 페이지 | 머리말/꼬리말이 모든 페이지에 반복되어 동일 내용 청크 생성 |
| overlap 설정 | 청킹 시 overlap 구간이 있으면 인접 청크 간 일부 내용이 중복됨 (near-duplicate) |
| 문서 재업로드 | 동일 PDF를 실수로 두 번 업로드하면 동일 청크가 두 버전으로 생성 |
| 덤프 PDF 중복 문제 | 여러 덤프 파일에 동일 기출 문제가 포함된 경우 |

### 3-4. 중복 처리 정책

| 중복 유형 | 처리 방침 |
|---------|----------|
| Exact duplicate (동일 버전 내) | 나중에 생성된 것은 `is_active = false`. `chunk_order`가 빠른 것 유지. |
| Exact duplicate (버전 간) | 최신 `document_version.version_number`의 청크만 `is_active = true`. 구버전 청크는 비활성화. |
| Near-duplicate | `quality_score`가 낮은 청크를 `is_active = false`로 비활성화. 동점이면 `created_at`이 오래된 것 유지. |

### 3-5. 중복 감지 실행 시점

파이프라인 Stage 5 완료 직후 즉시 실행한다. 별도 배치 스케줄이 아닌 파이프라인 워크플로의 마지막 단계로 포함한다.

---

## 4. 거버넌스 정책

### 4-1. 출처(Lineage) 추적

**배경**: DA 거버넌스의 핵심은 "이 데이터가 어디서 왔는가"를 추적하는 능력이다. Passly에서는 AI가 생성한 문제와 해설이 어떤 청크를 근거로 생성되었는지, 그 청크가 어떤 문서의 몇 번째 버전인지를 역추적할 수 있어야 한다.

**출처 계보 구조:**

```
certifications
  └── learning_documents (자격증별 업로드 PDF)
        └── document_versions (버전 이력)
              └── document_chunks (의미 단위 청크)
                    ├── chunk_embeddings (임베딩 벡터 + model_name + model_version)
                    └── questions.source_chunk_id (AI 생성 문제 출처)
                          └── answer_explanations.source_chunk_id (해설 출처)
```

**임베딩 모델 교체 이력 추적:**
- `chunk_embeddings.model_name`: 임베딩 생성 모델 식별자 (예: `text-embedding-004`)
- `chunk_embeddings.model_version`: 모델 버전 (예: `001`)
- 모델 교체 시 기존 임베딩은 삭제하지 않고 신규 임베딩을 생성 후 기존 레코드를 `is_deleted = true` 처리. 신규 임베딩은 새 레코드로 삽입.

**계보 조회 SQL — 특정 청크의 전체 출처 계보:**

```sql
-- 목적: 특정 청크 ID로부터 자격증까지 전체 출처 계보 조회
-- 용도: 검색 결과 출처 표시, AI 문제 근거 역추적
SELECT
    c.id                        AS certification_id,
    c.name                      AS certification_name,
    c.exam_code                 AS exam_code,
    ld.id                       AS document_id,
    ld.title                    AS document_title,
    ld.source_type              AS source_type,
    dv.id                       AS version_id,
    dv.version_number           AS version_number,
    dv.is_active                AS version_is_active,
    dc.id                       AS chunk_id,
    dc.chunk_order              AS chunk_order,
    dc.quality_score            AS quality_score,
    dc.access_level             AS access_level,
    ce.model_name               AS embedding_model,
    ce.model_version            AS embedding_model_version
FROM document_chunks dc
JOIN document_versions dv ON dv.id = dc.document_version_id
JOIN learning_documents ld ON ld.id = dv.learning_document_id
JOIN certifications c ON c.id = ld.certification_id
LEFT JOIN chunk_embeddings ce ON ce.chunk_id = dc.id
    AND ce.is_deleted = false
WHERE dc.id = :chunk_id  -- 조회 대상 청크 ID
  AND dc.is_deleted = false;
```

**AI 문제 출처 역추적 SQL:**

```sql
-- 목적: AI 생성 문제의 근거 청크 출처 계보 조회
SELECT
    q.id                        AS question_id,
    q.question_text             AS question_text,
    q.source_type               AS source_type,
    dc.id                       AS source_chunk_id,
    dc.chunk_text               AS source_chunk_text,
    ld.title                    AS source_document_title,
    dv.version_number           AS source_version
FROM questions q
LEFT JOIN document_chunks dc ON dc.id = q.source_chunk_id
    AND dc.is_deleted = false
LEFT JOIN document_versions dv ON dv.id = dc.document_version_id
LEFT JOIN learning_documents ld ON ld.id = dv.learning_document_id
WHERE q.id = :question_id
  AND q.is_deleted = false;
```

---

### 4-2. 버전 관리 정책

**배경**: 동일 문서(예: 2024년판 Azure AI-102 시험 가이드)를 2025년판으로 교체 업로드하는 상황이 발생한다. 이때 진행 중인 시험 세션이 있다면 구버전 청크를 즉시 삭제하면 안 된다. 세션이 참조하는 문제의 해설 출처 청크가 사라지면 해설 기능이 깨진다.

**버전 전환 절차:**

```
1. 신규 document_versions 레코드 생성 (version_number 증가, is_active = true)
2. 이전 document_versions.is_active = false 처리
3. 신규 pipeline_runs 생성 → 파이프라인 실행
4. 파이프라인 완료 시 신규 document_chunks/chunk_embeddings 생성
5. 구버전 청크: is_active = false 유지 (즉시 삭제 금지)
```

**구버전 청크 정리 조건:**

구버전 청크(`document_version.is_active = false` 버전 소속)를 정리(is_deleted = true 처리)하려면 아래 조건을 모두 충족해야 한다:
1. 해당 버전의 모든 `questions.source_chunk_id`를 참조하는 문제들이 관련된 `exam_sessions`이 모두 `is_completed = true`
2. 해당 버전의 `answer_explanations.source_chunk_id`를 참조하는 해설의 상위 문제들도 동일하게 완료 확인

**버전 간 활성 상태 일관성 검증 SQL (쿼리 #7):**

```sql
-- 목적: 1개 문서에 is_active=true인 버전이 2개 이상 존재하는 이상 상태 감지
-- 정상이면 0행 반환. 0행 초과 시 즉시 조사 필요.
-- 실행 주기: 문서 업로드/버전 전환마다
SELECT
    learning_document_id,
    COUNT(*) AS active_version_count
FROM document_versions
WHERE is_active = true
  AND is_deleted = false
GROUP BY learning_document_id
HAVING COUNT(*) > 1;
```

---

### 4-3. 접근 권한(Access Control) 정책

**배경**: 소규모 서비스지만 사용자가 개인적으로 업로드한 문서(예: 사내 내부 자료)를 다른 사용자와 공유하지 않으려는 경우가 있다. 청크 단위 접근 제어로 검색 시 권한 필터링을 가능하게 한다.

**설계 결정:**

| 항목 | 내용 |
|------|------|
| 배경 | 공유 자격증 자료(공식 가이드)는 모든 사용자가 활용해야 RAG 검색 품질이 높아진다. 그러나 일부 사용자가 비공개 자료를 업로드하는 상황도 지원해야 한다. |
| 선택 | `document_chunks.access_level` 컬럼(PRIVATE/SHARED)으로 청크 단위 접근 제어. |
| 근거 | 문서 단위(learning_documents)가 아닌 청크 단위 제어로 세분화하면, 동일 문서 내에서도 접근 수준을 달리 설정하는 확장이 가능하다. 현재는 문서 단위로 일괄 적용하나, 스키마 수준의 확장성을 확보한다. |
| 트레이드오프 | 청크 단위 접근 제어는 관리 복잡성이 증가한다. 소규모 서비스에서는 현실적으로 문서 단위 일괄 설정으로 운영하고, 컬럼 설계만 청크 단위로 준비한다. |

**코드값 정의 (docs/00-data-standard.md 섹션 5-6 기준):**

| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| PRIVATE | 비공개 | 업로드한 본인만 접근 가능 |
| SHARED | 공유 | 같은 자격증 학습자 전체 공유 |

**기본값**: `document_chunks.access_level DEFAULT 'SHARED'`
공식 가이드/덤프는 소규모 팀이 공유하는 것이 기본 목적이므로 SHARED를 기본값으로 설정한다.

**권한 적용 계층**: `document_chunks` 단위 (청크 레벨 세분화 지원)

**RAG 검색 시 접근 권한 필터:**

```sql
-- 목적: RAG 검색 시 접근 권한 필터 적용 예시
-- :current_user_id = 현재 로그인한 사용자 ID
WHERE dc.is_active = true
  AND dc.is_deleted = false
  AND dc.quality_score >= 60
  AND (
      dc.access_level = 'SHARED'    -- 전체 공유 청크
      OR (
          dc.access_level = 'PRIVATE'
          AND dv.learning_document_id IN (
              -- 해당 사용자가 업로드한 문서의 버전 ID 목록
              SELECT dv2.id
              FROM document_versions dv2
              JOIN learning_documents ld2 ON ld2.id = dv2.learning_document_id
              WHERE ld2.created_at IS NOT NULL  -- 업로더 추적 컬럼 확장 시 대체
          )
      )
  )
```

**users.access_level과의 관계:**
- `users.access_level = 'PRIVATE'`: 해당 사용자는 자신이 업로드한 문서의 청크에만 접근 가능. SHARED 청크도 접근 불가로 더 강한 제한.
- `users.access_level = 'SHARED'`: 모든 SHARED 청크 + 자신의 PRIVATE 청크 접근 가능.

> 주의: users.access_level과 document_chunks.access_level은 독립적으로 정의되어 있다. 실제 접근 로직은 두 값의 AND 조건으로 결정하며, 구체적인 비즈니스 규칙은 Wave 3 API 구현 단계에서 확정한다.

---

## 5. 품질 검증 쿼리 예시

> 모든 쿼리의 기대 결과: 정상 상태에서는 0행 반환. 1행 이상이면 이상 상태로 즉시 조사 필요.

---

### 쿼리 #1: exam_sessions.correct_count 정합성 검증

**목적**: `exam_sessions.correct_count` 반정규화 값과 `user_attempts` 집계 값의 불일치 감지.
docs/03-erd-physical.md 섹션 8 반정규화 결정 기록에서 이관.

**실행 주기**: 일 1회 배치 실행 (새벽 시간대)

```sql
-- 반정규화 정합성 검증: exam_sessions.correct_count vs user_attempts 집계
-- 정상이면 0행. 1행 이상이면 시험 완료 트랜잭션 버그 조사 필요.
SELECT
    es.id                                                    AS session_id,
    es.correct_count                                         AS stored_correct_count,
    COUNT(*) FILTER (WHERE ua.is_correct = true)             AS computed_correct_count,
    es.correct_count
        - COUNT(*) FILTER (WHERE ua.is_correct = true)       AS discrepancy
FROM exam_sessions es
JOIN user_attempts ua ON ua.session_id = es.id
    AND ua.is_deleted = false
WHERE es.is_completed = true
  AND es.is_deleted = false
GROUP BY es.id, es.correct_count
HAVING es.correct_count != COUNT(*) FILTER (WHERE ua.is_correct = true);
```

**기대 결과**: 0행 (불일치 없음)
**이상 감지 시 조치**: `discrepancy` 값과 `session_id`를 기록하고, 해당 세션의 완료 트랜잭션 로그 확인. `correct_count`를 `computed_correct_count`로 보정 UPDATE 처리.

---

### 쿼리 #2: quality_score 분포 조회 (등급별 청크 수)

**목적**: 전체 청크의 품질 등급 분포 현황 파악. 불량 비율이 높으면 파이프라인 청킹 파라미터 재검토 신호.

**실행 주기**: 파이프라인 완료 후 즉시

```sql
-- quality_score 등급별 청크 분포 현황
SELECT
    CASE
        WHEN quality_score IS NULL      THEN '미평가 (NULL)'
        WHEN quality_score >= 80        THEN '정상 (80~100)'
        WHEN quality_score >= 60        THEN '경고 (60~79)'
        ELSE                                 '불량 (0~59)'
    END                                 AS grade,
    COUNT(*)                            AS chunk_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS ratio_pct
FROM document_chunks
WHERE is_deleted = false
GROUP BY grade
ORDER BY
    CASE grade
        WHEN '정상 (80~100)' THEN 1
        WHEN '경고 (60~79)'  THEN 2
        WHEN '불량 (0~59)'   THEN 3
        ELSE 4
    END;
```

**기대 결과**: 정상 등급 비율 70% 이상 유지 권장. 불량 등급이 30% 초과하면 청킹 전략 재검토.

---

### 쿼리 #3: quality_score NULL인 청크 수 (파이프라인 미완료 감지)

**목적**: 파이프라인이 품질 평가 단계까지 완료되지 않은 청크 감지.

**실행 주기**: 파이프라인 완료 후 즉시

```sql
-- 파이프라인 미완료 청크 감지: quality_score가 NULL이면서 is_active=true인 청크
-- 정상이면 0행. pipeline_runs.status=COMPLETED 이후에도 NULL이 남으면 파이프라인 버그.
SELECT
    dc.id               AS chunk_id,
    dc.document_version_id,
    dc.chunk_order,
    dc.created_at,
    pr.status           AS pipeline_status,
    pr.error_message
FROM document_chunks dc
JOIN document_versions dv ON dv.id = dc.document_version_id
JOIN pipeline_runs pr ON pr.document_version_id = dv.id
WHERE dc.quality_score IS NULL
  AND dc.is_active = true
  AND dc.is_deleted = false
  AND pr.status = 'COMPLETED'  -- 파이프라인은 완료했는데 quality_score가 NULL
ORDER BY dc.created_at DESC;
```

**기대 결과**: 0행 (파이프라인 COMPLETED 상태에서 NULL 없음)
**이상 감지 시 조치**: 해당 `pipeline_runs.id`를 기록하고 Stage 5 품질 평가 단계 로그 확인.

---

### 쿼리 #4: pipeline_runs 실패율 계산 (문서별)

**목적**: 문서별 파이프라인 실패율 계산. 20% 초과 시 알림 대상.

**실행 주기**: 파이프라인 실행마다

```sql
-- pipeline_runs 실패율: 문서별 FAILED 비율 계산
-- fail_rate_pct > 20이면 알림 대상
SELECT
    ld.id                                                       AS document_id,
    ld.title                                                    AS document_title,
    ld.source_type,
    COUNT(*)                                                    AS total_runs,
    COUNT(*) FILTER (WHERE pr.status = 'COMPLETED')            AS completed_count,
    COUNT(*) FILTER (WHERE pr.status = 'FAILED')               AS failed_count,
    ROUND(
        COUNT(*) FILTER (WHERE pr.status = 'FAILED') * 100.0
            / NULLIF(COUNT(*), 0),
        2
    )                                                           AS fail_rate_pct,
    MAX(pr.error_message)                                       AS last_error_message
FROM pipeline_runs pr
JOIN learning_documents ld ON ld.id = pr.learning_document_id
WHERE pr.is_deleted = false
  AND ld.is_deleted = false
GROUP BY ld.id, ld.title, ld.source_type
HAVING ROUND(
    COUNT(*) FILTER (WHERE pr.status = 'FAILED') * 100.0 / NULLIF(COUNT(*), 0),
    2
) > 20
ORDER BY fail_rate_pct DESC;
```

**기대 결과**: 0행 (실패율 20% 이하)
**이상 감지 시 조치**: `last_error_message` 기반 원인 분류 후 섹션 2-2 처리 정책 적용.

---

### 쿼리 #5: exact duplicate 청크 감지 (MD5 해시)

**목적**: `chunk_text`가 완전히 동일한 중복 청크 감지.

**실행 주기**: 파이프라인 완료 후 즉시

```sql
-- Exact duplicate 청크 감지: MD5(chunk_text)가 동일한 청크 그룹
-- 정상이면 0행. 중복 발견 시 quality_score 낮은 쪽 또는 구버전 청크 비활성화.
SELECT
    md5(dc.chunk_text)      AS text_hash,
    COUNT(*)                AS duplicate_count,
    ARRAY_AGG(dc.id)        AS chunk_ids,
    ARRAY_AGG(DISTINCT dc.document_version_id) AS version_ids
FROM document_chunks dc
WHERE dc.is_active = true
  AND dc.is_deleted = false
GROUP BY md5(dc.chunk_text)
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

**기대 결과**: 0행 (exact duplicate 없음)
**이상 감지 시 조치**: `chunk_ids` 배열에서 최신 버전(`version_ids`에서 `version_number` 높은 것) 유지, 나머지 `is_active = false` 처리.

---

### 쿼리 #6: near-duplicate 청크 감지 (코사인 유사도 > 0.98)

**목적**: 의미적으로 거의 동일한 청크 감지. pgvector 코사인 유사도 연산자 활용.

**실행 주기**: 파이프라인 완료 후 즉시 (청크 수 1만 이하일 때만 전수 비교. 이상이면 샘플링 적용)

```sql
-- Near-duplicate 청크 감지: 코사인 유사도 > 0.98인 청크 쌍
-- pgvector <=> 연산자는 코사인 거리 반환 (0 = 동일, 2 = 정반대)
-- 코사인 거리 < 0.02 = 코사인 유사도 > 0.98
SELECT
    ce1.chunk_id            AS chunk_id_1,
    ce2.chunk_id            AS chunk_id_2,
    1 - (ce1.embedding <=> ce2.embedding) AS cosine_similarity,
    dc1.quality_score       AS quality_score_1,
    dc2.quality_score       AS quality_score_2
FROM chunk_embeddings ce1
JOIN chunk_embeddings ce2
    ON ce1.chunk_id < ce2.chunk_id  -- 중복 쌍 방지 (순서 고정)
    AND (ce1.embedding <=> ce2.embedding) < 0.02  -- 코사인 거리 < 0.02
JOIN document_chunks dc1 ON dc1.id = ce1.chunk_id
    AND dc1.is_active = true AND dc1.is_deleted = false
JOIN document_chunks dc2 ON dc2.id = ce2.chunk_id
    AND dc2.is_active = true AND dc2.is_deleted = false
WHERE ce1.is_deleted = false
  AND ce2.is_deleted = false
ORDER BY cosine_similarity DESC;
```

**기대 결과**: 0행 또는 최소 행 수
**이상 감지 시 조치**: `quality_score`가 낮은 청크를 `is_active = false` 처리. 동점이면 `chunk_id_2`(나중 생성) 비활성화.

---

### 쿼리 #7: 버전 활성 상태 일관성 검증

**목적**: 1개 문서에 `is_active = true`인 버전이 2개 이상 존재하는 이상 상태 감지.

**실행 주기**: 문서 업로드마다 (버전 전환 직후)

```sql
-- 버전 활성 상태 일관성: 1개 문서에 is_active=true 버전이 2개 이상인 경우 감지
-- 정상이면 0행. 버전 전환 트랜잭션 버그 조사 필요.
SELECT
    dv.learning_document_id,
    ld.title                    AS document_title,
    COUNT(*)                    AS active_version_count,
    ARRAY_AGG(dv.version_number ORDER BY dv.version_number) AS active_versions
FROM document_versions dv
JOIN learning_documents ld ON ld.id = dv.learning_document_id
WHERE dv.is_active = true
  AND dv.is_deleted = false
GROUP BY dv.learning_document_id, ld.title
HAVING COUNT(*) > 1;
```

**기대 결과**: 0행 (문서당 활성 버전 1개)
**이상 감지 시 조치**: `active_versions` 배열에서 최신 버전 번호만 `is_active = true` 유지, 나머지 `is_active = false` 처리.

---

### 쿼리 #8: exam_domains 가중치 합산 검증

**목적**: 자격증별 `exam_domains.weight_percent` 합계가 100이 되는지 확인. DB CHECK 제약은 행 단위만 가능하므로 합산 검증은 앱/쿼리 레벨에서 수행한다.

**실행 주기**: 자격증 데이터(exam_domains) 변경 시

```sql
-- exam_domains 가중치 합산 검증: 자격증별 weight_percent 합계가 100인지 확인
-- 정상이면 0행. 합계가 100이 아닌 자격증 목록 반환.
SELECT
    c.id                        AS certification_id,
    c.name                      AS certification_name,
    c.exam_code,
    SUM(ed.weight_percent)      AS total_weight,
    SUM(ed.weight_percent) - 100 AS deviation
FROM certifications c
JOIN exam_domains ed ON ed.certification_id = c.id
    AND ed.is_deleted = false
WHERE c.is_deleted = false
GROUP BY c.id, c.name, c.exam_code
HAVING SUM(ed.weight_percent) != 100;
```

**기대 결과**: 0행 (모든 자격증의 가중치 합계가 100)
**이상 감지 시 조치**: `deviation` 값을 확인하고 `exam_domains.weight_percent` 수정 후 재검증.

---

### 쿼리 #9: user_attempts 불변성 검증

**목적**: `user_attempts.is_deleted = true`인 레코드가 존재하는지 감지. 절대 금지 항목 위반 감시.

**실행 주기**: 주 1회 (정기 배치)

```sql
-- user_attempts 불변성 검증: is_deleted=true 레코드 감지
-- 정상이면 0행. 1행 이상이면 AGENTS.md 절대 금지 항목 위반 — 즉시 조사 필요.
SELECT
    ua.id                   AS attempt_id,
    ua.session_id,
    ua.question_id,
    ua.is_correct,
    ua.answered_at,
    ua.updated_at           AS deleted_at  -- 삭제 처리된 시점 추정
FROM user_attempts ua
WHERE ua.is_deleted = true;
```

**기대 결과**: 0행 (user_attempts.is_deleted는 항상 false)
**이상 감지 시 조치**: 즉각 조사 필요. 어떤 API 또는 배치가 `is_deleted = true`를 설정했는지 확인하고 해당 로직 제거. `is_deleted`를 다시 `false`로 복구.

---

### 쿼리 #10: 청크-임베딩 정합성 검증

**목적**: `document_chunks` 수와 `chunk_embeddings` 수가 일치하는지 확인. 임베딩 생성이 누락된 청크 감지.

**실행 주기**: 파이프라인 완료 후 즉시

```sql
-- 청크-임베딩 정합성: 활성 청크에 대응하는 임베딩이 모두 존재하는지 확인
-- 정상이면 0행. 임베딩 없는 청크가 있으면 파이프라인 Stage 4(임베딩 생성) 버그.
SELECT
    dc.id                   AS chunk_id,
    dc.document_version_id,
    dc.chunk_order,
    dc.quality_score,
    dc.created_at
FROM document_chunks dc
LEFT JOIN chunk_embeddings ce
    ON ce.chunk_id = dc.id
    AND ce.is_deleted = false
WHERE dc.is_active = true
  AND dc.is_deleted = false
  AND ce.id IS NULL;  -- 임베딩이 없는 청크
```

**기대 결과**: 0행 (모든 활성 청크에 임베딩 존재)
**이상 감지 시 조치**: 누락된 `chunk_id` 목록으로 임베딩 재생성 파이프라인 실행.

---

## 6. 정기 검증 스케줄

| 검증 항목 | 쿼리 번호 | 주기 | 실행 방법 | 알림 조건 |
|---------|----------|------|---------|---------|
| correct_count 정합성 | #1 | 일 1회 (배치) | 새벽 배치 스크립트 | 1행 이상 반환 시 |
| quality_score 분포 | #2 | 파이프라인 완료 후 즉시 | 파이프라인 워크플로 내 | 불량 비율 30% 초과 시 |
| quality_score NULL 청크 | #3 | 파이프라인 완료 후 즉시 | 파이프라인 워크플로 내 | 1행 이상 반환 시 |
| 파싱 실패율 | #4 | 파이프라인 실행마다 | 파이프라인 워크플로 내 | fail_rate_pct > 20 |
| exact duplicate 감지 | #5 | 파이프라인 완료 후 즉시 | 파이프라인 워크플로 내 | 1행 이상 반환 시 |
| near-duplicate 감지 | #6 | 파이프라인 완료 후 즉시 | 파이프라인 워크플로 내 | 1행 이상 반환 시 |
| 버전 정합성 | #7 | 문서 업로드마다 | 업로드 API 후처리 | 1행 이상 반환 시 |
| 가중치 합산 | #8 | 자격증 데이터 변경 시 | 관리 API 후처리 | 1행 이상 반환 시 |
| user_attempts 불변성 | #9 | 주 1회 | 정기 배치 스크립트 | 1행 이상 반환 시 (CRITICAL) |
| 청크-임베딩 정합성 | #10 | 파이프라인 완료 후 즉시 | 파이프라인 워크플로 내 | 1행 이상 반환 시 |

**알림 방법 (현재 단계 기준):**
- 소규모(2~10명) 서비스 특성상 별도 모니터링 플랫폼 없이 파이프라인 로그 파일 및 콘솔 출력으로 관리.
- Wave 5 이후 GCP 배포 시 Cloud Monitoring 연동을 고려한다.

---

## 7. 절대 금지 사항

> AGENTS.md 섹션 5 절대 금지 항목을 데이터 품질 관점에서 재정의한다.
> 이 문서를 참조하는 모든 개발자 및 운영자는 아래 금지 사항을 준수해야 한다.

| 번호 | 금지 행위 | 위반 시 영향 | 검증 쿼리 |
|------|---------|------------|---------|
| DQ-01 | `user_attempts` 레코드 DELETE | 오답 분석 이력 소실, 학습 통계 신뢰성 파괴 | 쿼리 #9 |
| DQ-02 | `user_attempts.is_deleted = true` 변경 | DQ-01과 동일 영향. 소프트 삭제도 금지. | 쿼리 #9 |
| DQ-03 | ERD 없이 테이블 신규 생성 | 설계 정합성 붕괴, 다른 테이블과의 관계 미정의 상태 | - |
| DQ-04 | metadata 없는 pgvector index 설계 | 검색 필터 불가, 모델 교체 이력 추적 불가 | - |
| DQ-05 | 구버전 document_chunks 즉시 삭제 | 진행 중인 exam_sessions 해설 링크 파괴 | 쿼리 #7 |
| DQ-06 | exam_sessions 완료 트랜잭션 분리 처리 | correct_count 반정규화 불일치 발생 | 쿼리 #1 |
| DQ-07 | quality_score NULL 청크 RAG 검색 포함 | 품질 미검증 청크가 LLM 컨텍스트에 포함되어 답변 품질 저하 | 쿼리 #3 |

---

## 참조 문서

| 문서 | 관련 섹션 |
|------|---------|
| docs/00-data-standard.md | 표준 용어 사전, ACCESS_LEVEL 코드 정의 |
| docs/02-erd-logical.md | 결정 3 (correct_count 반정규화), 결정 4 (user_attempts 불변), 결정 1 (document_versions 분리) |
| docs/03-erd-physical.md | 섹션 8 반정규화 결정 기록, 섹션 7 제약조건 목록 |
| docs/04-vector-schema.md | chunk_embeddings 스키마, 메타데이터 필드 설계 |
| docs/05-rag-pipeline.md | Stage 5 품질 평가 단계, quality_score 5개 지표 |
| AGENTS.md | 섹션 5 절대 금지 사항, 섹션 4 명명 규칙 |
