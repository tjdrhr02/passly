# Passly 데이터 표준서

> 버전: 1.0 | 작성일: 2025-06 | 작성자: 개발자
> 이 문서는 Passly 프로젝트의 모든 데이터 설계의 기준이 된다.
> 코드 작성 전, ERD 설계 전 반드시 이 문서를 읽고 따른다.

---

## 1. 표준 용어 사전

Passly 도메인에서 사용하는 핵심 용어를 정의한다.
동일한 개념을 다르게 부르면 데이터 정합성 문제가 발생한다.

| 용어 (영문) | 용어 (한글) | 정의 |
|------------|------------|------|
| Certification | 자격증 | 사용자가 학습하고자 하는 자격증. 예: Azure AI Engineer Associate |
| ExamDomain | 시험 영역 | 자격증의 출제 영역. 예: "AI 솔루션 설계" (가중치 포함) |
| Topic | 학습 개념 | 시험 영역 내 세부 학습 주제. 예: "Azure OpenAI Service" |
| LearningDocument | 학습 문서 | 업로드된 PDF 원본. 시험 가이드 또는 덤프 |
| DocumentChunk | 문서 청크 | 학습 문서를 의미 단위로 분할한 조각. RAG 검색의 최소 단위 |
| ChunkEmbedding | 청크 임베딩 | 문서 청크를 벡터로 변환한 수치 표현 (pgvector 저장) |
| DumpQuestion | 덤프 문제 | 덤프 PDF에서 파싱된 실제 기출/예상 문제 |
| GeneratedQuestion | AI 생성 문제 | 시험 가이드와 덤프를 기반으로 AI가 생성한 문제 |
| Choice | 선택지 | 객관식 문제의 선택 항목 |
| AnswerExplanation | 정답 해설 | 정답과 해설 텍스트. 출처 chunk 참조 포함 |
| ExamSession | 시험 세션 | 사용자가 시작한 하나의 시험 응시 단위 |
| UserAttempt | 풀이 이력 | 시험 세션 내 개별 문제에 대한 응답 기록 |
| PipelineRun | 파이프라인 실행 | PDF 업로드 후 파싱→청킹→임베딩→색인 전체 처리 단위 |
| QualityScore | 품질 점수 | 문서 청크의 검색 적합성 품질을 0~100으로 표현 |

---

## 2. 명명 규칙

### 2-1. 테이블명
| 규칙 | 예시 (올바름) | 예시 (틀림) |
|------|--------------|-------------|
| snake_case | `exam_sessions` | `ExamSessions` |
| 복수형 | `certifications` | `certification` |
| 영문 소문자 | `user_attempts` | `UserAttempts` |
| 축약 금지 | `certifications` | `certs` |

### 2-2. 컬럼명
| 규칙 | 예시 (올바름) | 예시 (틀림) |
|------|--------------|-------------|
| snake_case | `created_at` | `createdAt` |
| 영문 소문자 | `is_correct` | `IsCorrect` |
| 의미 명확 | `answered_at` | `time` |
| 불리언: is_ / has_ 접두사 | `is_deleted`, `has_explanation` | `deleted`, `explanation` |

### 2-3. PK / FK
| 대상 | 규칙 | 예시 |
|------|------|------|
| PK | 모든 테이블 `id` 컬럼, UUID | `id UUID DEFAULT gen_random_uuid()` |
| FK | `참조테이블_단수형_id` | `certification_id`, `user_id` |
| FK 축약 금지 | `certification_id` | `cert_id` |

### 2-4. 인덱스명
```
idx_{테이블명}_{컬럼명}
idx_{테이블명}_{컬럼1}_{컬럼2}  (복합 인덱스)

예시:
  idx_questions_certification_id
  idx_user_attempts_session_id_is_correct
  idx_document_chunks_embedding  (pgvector)
```

### 2-5. API 경로
| 규칙 | 예시 (올바름) | 예시 (틀림) |
|------|--------------|-------------|
| kebab-case | `/api/exam-sessions` | `/api/examSessions` |
| 복수형 리소스 | `/api/certifications` | `/api/certification` |
| 동사 금지 (RESTful) | `POST /api/questions` | `/api/createQuestion` |

### 2-6. React 컴포넌트 / 파일
| 대상 | 규칙 | 예시 |
|------|------|------|
| 컴포넌트 파일 | PascalCase.tsx | `ExamQuestion.tsx` |
| 훅 파일 | use + PascalCase.ts | `useExamSession.ts` |
| API 클라이언트 | camelCase.ts | `examApi.ts` |
| 타입 파일 | camelCase.types.ts | `exam.types.ts` |

---

## 3. 표준 도메인 정의

모든 컬럼 설계 시 아래 도메인 기준을 따른다.

| 도메인명 | PostgreSQL 타입 | 길이/정밀도 | 사용 기준 |
|---------|----------------|------------|---------|
| ID | UUID | - | 모든 PK, UUID v4 |
| 짧은 이름 | VARCHAR | 100 | 자격증명, 영역명 등 |
| 일반 이름 | VARCHAR | 255 | 문서 제목, 사용자 이름 |
| 긴 텍스트 | TEXT | - | 문제 본문, 해설, 청크 텍스트 |
| 일시 | TIMESTAMPTZ | - | 모든 시각 정보 (타임존 포함) |
| 날짜 | DATE | - | 날짜만 필요한 경우 |
| 정수 | INTEGER | - | 카운트, 순번 |
| 점수/비율 | NUMERIC | (5,2) | 품질점수, 정답률 (0.00~100.00) |
| 불리언 | BOOLEAN | - | 참/거짓 상태 |
| 벡터 | vector | (768) | pgvector 임베딩 |
| JSON | JSONB | - | 구조가 유동적인 메타데이터 |

---

## 4. 표준 공통 컬럼

모든 테이블은 아래 컬럼을 반드시 포함한다.

```sql
id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
is_deleted  BOOLEAN     NOT NULL DEFAULT false
```

### 적용 원칙
- `is_deleted = true`로 소프트 삭제. 물리 삭제 금지.
- `updated_at`은 트리거 또는 애플리케이션 레벨에서 자동 갱신.
- `user_attempts`는 시험 이력이므로 is_deleted 값을 true로 바꾸는 것도 금지 (불변 이력).

---

## 5. 코드 테이블 정의

고정된 값 목록은 코드 테이블(`code_values`)로 관리한다.
코드값을 컬럼에 직접 하드코딩하지 않는다.

### 5-1. DIFFICULTY (난이도)
| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| BASIC | 기본 | 개념 이해 수준 문제 |
| INTERMEDIATE | 중급 | 응용 및 시나리오 문제 |
| ADVANCED | 고급 | 복합 시나리오, 설계 판단 문제 |

### 5-2. SOURCE_TYPE (자료 유형)
| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| OFFICIAL_GUIDE | 공식 가이드 | MS Learn 등 공식 시험 가이드 PDF |
| DUMP | 덤프 | 기출/예상 문제 모음 PDF |
| GENERATED | AI 생성 | 시스템이 자동 생성한 문제 |

### 5-3. QUESTION_TYPE (문제 유형)
| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| SINGLE | 단일 선택 | 보기 중 1개 선택 |
| MULTIPLE | 복수 선택 | 보기 중 N개 선택 (문제에 명시) |
| SCENARIO | 시나리오 | 상황 제시 후 최적 선택 |

### 5-4. PIPELINE_STATUS (파이프라인 상태)
| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| PENDING | 대기 | 처리 대기 중 |
| PROCESSING | 처리 중 | 파싱/청킹/임베딩 진행 중 |
| COMPLETED | 완료 | 모든 처리 완료 |
| FAILED | 실패 | 처리 중 오류 발생 |

### 5-5. EXAM_MODE (시험 모드)
| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| TIMED | 실전 모드 | 실제 시험 시간 타이머 적용 |
| PRACTICE | 연습 모드 | 타이머 없음, 즉시 해설 |
| REVIEW | 복습 모드 | 오답 문제 재풀이 |

### 5-6. ACCESS_LEVEL (접근 수준)
| 코드값 | 한글명 | 설명 |
|--------|--------|------|
| PRIVATE | 비공개 | 업로드한 본인만 접근 |
| SHARED | 공유 | 같은 자격증 학습자 공유 |

---

## 6. 이력 테이블 설계 원칙

변경 이력 추적이 필요한 엔터티는 별도 이력 테이블을 설계한다.

### 이력 테이블 적용 기준
| 기준 | 예시 |
|------|------|
| "언제 어떻게 바뀌었는가"가 중요한 데이터 | document_versions |
| 삭제해도 기록이 남아야 하는 데이터 | user_attempts (불변) |
| 집계/분석 대상이 되는 이벤트 데이터 | exam_sessions |

### Passly 이력 테이블 목록
| 이력 테이블 | 추적 대상 | 특이사항 |
|------------|----------|---------|
| `document_versions` | 문서 재업로드/갱신 이력 | 버전별 청크 연결 |
| `user_attempts` | 문제 응답 이력 | is_deleted 변경도 금지 |
| `pipeline_runs` | 파이프라인 실행 이력 | 실패 로그 포함 |

---

## 7. 데이터 표준 검증 체크리스트

코드 작성 또는 DDL 작성 전 아래를 확인한다.

- [ ] 새 엔터티 이름이 표준 용어 사전에 없다면 추가했는가
- [ ] 테이블명이 snake_case + 복수형인가
- [ ] PK가 id UUID인가
- [ ] 공통 컬럼 4개가 모두 있는가
- [ ] FK 이름이 `참조테이블_단수형_id` 형식인가
- [ ] 고정 값 목록이 코드 테이블로 관리되는가
- [ ] 이력 추적이 필요한 엔터티에 이력 테이블이 있는가