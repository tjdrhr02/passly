# Passly — AGENTS.md
> Claude와 Cursor가 공통으로 읽는 단일 원칙 파일.
> 작업 시작 전 반드시 전체를 읽을 것.

---

## 1. 프로젝트 목적

### 1-1. 앱 목적
자격증 공식 시험 가이드 PDF와 덤프 PDF를 업로드하면
실전 시험 / 연습 / 오답 확인 / AI 질문을 제공하는 자격증 문제풀이 플랫폼.

- 대상 유저: 소수(2~10명), 다중 접속 지원
- 기본 자격증: Azure AI Engineer Associate (확장 가능 구조)
- UI: 깔끔한 SaaS 스타일 (Notion, Linear 느낌)

### 1-2. 포트폴리오 목적
개발자 → DA(Data Architect) 포지션 전환을 위한 실전 포트폴리오.

| 영역 | 비중 | 증명 내용 |
|------|------|----------|
| 전통 DA | 40% | 데이터 표준화, ERD + 설계 근거, 정규화/반정규화, 이력/코드 테이블 |
| Cloud DA | 25% | GCP 아키텍처, Cloud Run/SQL/Storage 선택 근거, ADR |
| AI DA | 25% | pgvector Vector Index, RAG 파이프라인, Hybrid Search, 검색 품질 평가 |
| 컨설팅/ISP | 10% | 요구사항 정의서, As-Is/To-Be, ADR |

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| Frontend | React + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| Backend | FastAPI (Python) + SQLAlchemy + Alembic |
| Database | PostgreSQL + pgvector (로컬: Docker / GCP: Cloud SQL) |
| Embedding | Gemini Developer API (로컬) / Vertex AI (GCP) |
| LLM | Gemini Developer API (로컬) / Vertex AI Gemini (GCP) |
| PDF 파싱 | PyMuPDF |
| Infra (로컬) | Docker Compose |
| Infra (GCP) | Cloud Run + Cloud SQL + Cloud Storage + Secret Manager |

### 로컬 ↔ GCP 전환 원칙
환경변수 하나로 전환. 코드 변경 없음.
```
USE_VERTEX_AI=false  → 로컬 (Gemini API 키)
USE_VERTEX_AI=true   → GCP (서비스 계정)
```

---

## 3. 페이지 구조

```
/              대시보드 — 학습 현황, 오답률 Top3
/upload        자료 업로드 — PDF, 파이프라인 진행 표시
/exam          실전 시험 — 타이머 + 셔플 + 일괄 채점 + 해설
/practice      연습 모드 — 영역 선택, AI 문제 생성, 즉시 해설
/review        오답 노트 — 시험 이력, 오답 재확인
/chat          AI 질문 (선택) — RAG + 출처 표시
```

---

## 4. 데이터 표준 원칙
> 상세 내용: docs/00-data-standard.md

### 명명 규칙
| 대상 | 규칙 | 예시 |
|------|------|------|
| 테이블 | snake_case + 복수형 | `exam_sessions` |
| 컬럼 | snake_case | `created_at` |
| PK | `id UUID DEFAULT gen_random_uuid()` | |
| FK | `참조테이블_단수형_id` | `certification_id` |
| 인덱스 | `idx_테이블_컬럼` | `idx_chunks_topic_id` |
| 코드값 | UPPER_SNAKE_CASE | `DIFFICULTY_BASIC` |
| API | kebab-case | `/api/exam-sessions` |
| React 컴포넌트 | PascalCase.tsx | `ExamQuestion.tsx` |
| React 훅 | use + PascalCase.ts | `useExamSession.ts` |

### 공통 컬럼 (모든 테이블 필수)
```sql
id          UUID        PRIMARY KEY DEFAULT gen_random_uuid()
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
is_deleted  BOOLEAN     NOT NULL DEFAULT false
```

### 코드 테이블 대상
- DIFFICULTY: BASIC / INTERMEDIATE / ADVANCED
- SOURCE_TYPE: OFFICIAL_GUIDE / DUMP / GENERATED
- QUESTION_TYPE: SINGLE / MULTIPLE / SCENARIO
- PIPELINE_STATUS: PENDING / PROCESSING / COMPLETED / FAILED
- EXAM_MODE: TIMED / PRACTICE / REVIEW
- ACCESS_LEVEL: PRIVATE / SHARED

---

## 5. 하네스 — 작업 규칙

### 문서 우선 원칙 (절대 순서)
```
요구사항 정의 → 개념 모델 → 논리 ERD → 물리 ERD → DDL → 코드
```

### 절대 금지
- ERD 없이 테이블 먼저 만들기
- docs/ 업데이트 없이 코드 변경
- metadata 없는 pgvector index 설계
- UI 먼저 만들기 (API 미구현 상태)
- 설계 근거 없이 결정 넘어가기
- review-agent 검토 없이 다음 작업 진행
- user_attempts 레코드 삭제 또는 is_deleted = true 변경

---

## 6. Hook 정의

### 실제 자동화 훅 (settings.local.json — 하네스가 직접 실행)
> 구현 스크립트: `.claude/hooks/`

| 이벤트 | 스크립트 | 동작 |
|--------|---------|------|
| PreToolUse (Write\|Edit) | hooks/gate-review.py | `.py/.ts/.tsx/.sql` 수정 전 `.REVIEW_REQUIRED` 존재 시 **BLOCK** (exit 2) |
| PostToolUse (Write\|Edit) | hooks/queue-review.py | `.py/.ts/.tsx/.sql` 수정 후 `.REVIEW_REQUIRED` 마커 생성 |
| Stop | hooks/run-review.sh | 세션 종료 시 `.REVIEW_REQUIRED` 있으면 터미널에 컬러 경고 출력 |

**Review Gate 해제 방법**: review-agent PASS 후 `rm .REVIEW_REQUIRED`

### 소프트 지침 훅 (hookify.*.local.md — Claude가 컨텍스트로 읽음)

| 훅 파일 | 트리거 | 목적 |
|---------|--------|------|
| hookify.pre-implementation | `.py/.ts/.tsx` 파일 생성/수정 | 관련 docs 존재 확인 |
| hookify.post-implementation | 작업 완료(stop) | review-agent 호출 확인 |
| hookify.pre-db-change | alembic/migration/`.sql` 파일 | ERD 문서 최신 상태 확인 |
| hookify.pre-vector-index | `vector(`, `IVFFlat` 등 패턴 | metadata 필드 완전성 확인 |
| hookify.pre-api | `routers/*.py` 파일 | 스키마 정의 확인 |
| hookify.pre-component | `components/*.tsx` 파일 | API 구현 여부 + 타입 확인 |

---

## 7. Sub-agent 역할

| Agent | 역할 | 활성 Wave |
|-------|------|-----------|
| design-agent | 데이터 표준, ERD, 아키텍처 설계 | Wave 1 |
| pipeline-agent | PDF 파싱, chunking, embedding | Wave 3 |
| api-agent | FastAPI 엔드포인트 구현 | Wave 3-4 |
| frontend-agent | React 컴포넌트, 페이지 구현 | Wave 4 |
| rag-agent | 검색, 답변 생성, 품질 평가 | Wave 4 |
| review-agent | 모든 구현물 코드/설계 검토 | Wave 2-5 전체 |

### review-agent 체크리스트
```
[ ] AGENTS.md 원칙 위반 없음
[ ] 명명 규칙 준수
[ ] 공통 컬럼 4개 존재 (id, created_at, updated_at, is_deleted)
[ ] docs/와 코드 일치
[ ] API 에러 핸들링 존재
[ ] 하드코딩 없음 (URL, secret, magic number)
[ ] TypeScript any 없음
[ ] pgvector 사용 시 metadata 필드 완전
[ ] user_attempts 삭제 로직 없음
```

### review-agent 결과 형식
```
## Review Result
상태: PASS / FAIL / CONDITIONAL PASS

발견된 문제:
- [CRITICAL] ... → 반드시 수정 후 재검토
- [WARNING]  ... → 권고 수정
- [INFO]     ... → 참고 사항
```

### 메인 에이전트 → review-agent 호출 형식
```
@review-agent
구현 완료: [작업명]
변경 파일: [파일 경로]
관련 docs: [참조 문서]
특이사항: [있으면 기재]
```

---

## 8. 워크플로 (Wave)

### Wave 1 — 설계 (순차, 전체 완료 필수)
- [ ] docs/00-data-standard.md ✅ (완료)
- [ ] docs/01-requirements.md ✅ (완료)
- [ ] docs/02-erd-logical.md ✅ (완료)
- [ ] docs/03-erd-physical.md ✅ (완료)
- [ ] docs/04-vector-schema.md ✅ (완료)
- [ ] docs/05-rag-pipeline.md ✅ (완료)
- [ ] docs/06-data-quality.md ✅ (완료)
- [ ] docs/09-adr.md ✅ (완료)

### Wave 2 — 환경 세팅 ✅ (완료)
| 브랜치 | 작업 | 상태 |
|--------|------|------|
| wave2-infra | Docker Compose 세팅 | ✅ |
| wave2-db | DDL + Alembic migration | ✅ |
| wave2-fe-scaffold | React + Vite + Tailwind + shadcn/ui | ✅ |

### Wave 3 — 백엔드 핵심 ✅ (완료)
| 브랜치 | 작업 | 상태 |
|--------|------|------|
| wave3-pipeline | PDF 파싱(parser.py) → 청킹(chunker.py) → 임베딩(embedder.py) → 품질평가(quality.py) → 색인(indexer.py) → 오케스트레이터(pipeline.py) | ✅ |
| wave3-api-base | FastAPI 기본 구조 + JWT 인증(auth.py) | ✅ |

### Wave 4 — 기능 구현 ✅ (완료)
| 브랜치 | 작업 | 상태 |
|--------|------|------|
| wave4-upload | POST /api/documents/upload + GET /api/documents + 파이프라인 BackgroundTasks 연동 + UploadPage.tsx | ✅ |
| wave4-exam | POST /api/exam-sessions + GET questions + POST submit + GET result + ExamPage.tsx (타이머+셔플+채점+해설) | ✅ |
| wave4-practice | POST /api/practice/generate + POST /api/practice/submit + PracticePage.tsx (즉시 채점+해설) | ✅ |
| wave4-review | GET /api/exam-sessions + GET attempts + GET wrong-attempts + ReviewPage.tsx (오답토글+해설) | ✅ |
| wave4-dashboard | GET /api/analytics/summary + recent-sessions + weak-domains + DashboardPage.tsx | ✅ |
| wave4-chat | GET /api/chat (Hybrid Search + Gemini 답변) + RAG retriever/generator + ChatPage.tsx (출처 패널) | ✅ |

### Wave 5 — 통합 + 산출물
- [x] Hybrid Search recall@10 측정 + Vector 단독 비교 ✅ (완료 — docs/07-search-evaluation.md)
- [x] 검색 품질 평가 (docs/07-search-evaluation.md 작성) ✅ (완료)
- [x] retriever.py unified search() 인터페이스 + quality_score>=60 + probes=15 ✅ (완료)
- [ ] GCP 배포 검증 (Cloud Run + Cloud SQL + Cloud Storage)
- [ ] README 완성 (포트폴리오 소개 + 아키텍처 다이어그램)

---

## 9. Skills
> `skills/{name}/SKILL.md` 구조로 관리. 하네스가 자동 인식.

| Skill | 사용 시점 |
|-------|-----------|
| erd-review | ERD 작성/검토 시 |
| normalization | 정규화/반정규화 판단 시 |
| pgvector-design | pgvector 스키마 설계 시 |
| pdf-parsing | PDF 파싱 구현 시 |
| api-review | FastAPI 엔드포인트 검토 시 |
| fe-review | React 컴포넌트 검토 시 |
| search-eval | 검색 품질 평가 시 |
| docs-sync | 코드베이스/레포 기준 전체 문서 동기화 + AGENTS.md 갱신 시 |

---

## 10. 필수 산출물

| 산출물 | 파일 | DA 영역 |
|--------|------|---------|
| 데이터 표준서 | docs/00-data-standard.md | 전통 DA |
| 요구사항 정의서 | docs/01-requirements.md | 컨설팅 |
| 논리 ERD + 근거 | docs/02-erd-logical.md | 전통 DA |
| 물리 ERD / DDL | docs/03-erd-physical.md | 전통 DA |
| pgvector Schema | docs/04-vector-schema.md | AI DA |
| RAG Pipeline | docs/05-rag-pipeline.md | AI DA |
| 데이터 품질 규칙 | docs/06-data-quality.md | 거버넌스 |
| 검색 평가 결과 | docs/07-search-evaluation.md | AI DA |
| ADR | docs/09-adr.md | Cloud DA |
| README | README.md | 첫인상 |