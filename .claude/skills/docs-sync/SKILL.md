---
name: docs-sync
description: 현재 코드베이스/레포지토리 상태를 기준으로 docs/ 문서 전체를 동기화한다. 구현 후 docs가 최신인지 확인하거나, AGENTS.md Wave 진행 상황을 갱신할 때 호출.
version: 1.0.0
---

# Skill: 문서 동기화 (docs-sync)

## 사용 시점
- 구현 완료 후 docs/ 내용이 코드와 일치하는지 확인할 때
- AGENTS.md의 Wave 진행 체크리스트를 현재 상태로 갱신할 때
- 신규 파일/테이블/엔드포인트 추가 후 관련 문서 업데이트가 필요할 때
- `/docs-sync` 명령으로 직접 호출할 때

---

## 실행 절차

### Step 1 — 현재 파일 트리 스캔
```bash
find /Users/fairytale/dev/passly -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' | sort
```

### Step 2 — docs/ 존재 여부 확인
아래 파일이 실제로 존재하는지 확인하고 AGENTS.md 체크리스트와 대조한다.

| 파일 | Wave | 기대 상태 |
|------|------|---------|
| docs/00-data-standard.md | Wave 1 | 완료 |
| docs/01-requirements.md | Wave 1 | 완료 |
| docs/02-erd-logical.md | Wave 1 | 완료 |
| docs/03-erd-physical.md | Wave 1 | 완료 |
| docs/04-vector-schema.md | Wave 1 | 미완료 |
| docs/05-rag-pipeline.md | Wave 1 | 미완료 |
| docs/06-data-quality.md | Wave 1 | 미완료 |
| docs/09-adr.md | Wave 1 | 완료 |

### Step 3 — 코드 파일 ↔ docs 정합성 검사

#### DDL / 마이그레이션 파일이 있을 경우
```bash
find . -name '*.sql' -o -name 'versions/*.py' | sort
```
- DDL 테이블 목록이 `docs/03-erd-physical.md` 테이블 목록과 일치하는가?
- 컬럼 추가/삭제가 docs에 반영됐는가?

#### FastAPI 라우터가 있을 경우
```bash
find . -path '*/api/routers/*.py' | sort
```
- 각 라우터가 docs에 API 명세로 기록돼 있는가?

#### React 컴포넌트/페이지가 있을 경우
```bash
find . -path '*/src/pages/*.tsx' -o -path '*/src/components/*.tsx' | sort
```
- 각 페이지가 `docs/01-requirements.md` 페이지 구조와 일치하는가?

#### pgvector 사용 코드가 있을 경우
```bash
grep -r 'vector(' . --include='*.py' --include='*.sql' -l
```
- `docs/04-vector-schema.md`가 존재하고 최신인가?

### Step 4 — AGENTS.md Wave 체크리스트 갱신

파일 존재 여부와 내용을 확인한 뒤 AGENTS.md의 `[ ]`를 `[x]` / `✅ (완료)`로 갱신한다.

갱신 형식:
```
- [ ] docs/XX-name.md            ← 미완료
- [ ] docs/XX-name.md ✅ (완료)  ← 완료 (파일 존재 + 내용 충실)
```

### Step 5 — 문서 헤더 버전/날짜 확인

각 docs 파일 상단 버전/작성일이 마지막 수정 내용과 맞는지 확인한다.
오래된 날짜가 있으면 현재 날짜로 갱신한다.

### Step 6 — 동기화 결과 보고

```
## docs-sync 결과

### 파일 존재 여부
| 문서 | 상태 |
|------|------|
| docs/00-data-standard.md | ✅ 존재 |
| ... | ... |

### 정합성 이슈
- [STALE] docs/03-erd-physical.md — DDL에 chunk_topics 테이블 추가됐으나 문서 미반영
- [MISSING] docs/04-vector-schema.md — 코드에 pgvector 사용하지만 문서 없음

### AGENTS.md 갱신 사항
- docs/03-erd-physical.md → ✅ (완료) 로 갱신

### 권고 조치
- [ ] docs/04-vector-schema.md 작성 필요
- [ ] docs/05-rag-pipeline.md 작성 필요
```

---

## 자동 갱신 가능 항목 vs 수동 검토 필요 항목

| 항목 | 자동 갱신 가능 | 수동 검토 필요 |
|------|-------------|-------------|
| AGENTS.md 체크리스트 | ✅ 파일 존재 시 | - |
| 문서 헤더 날짜 | ✅ | - |
| 테이블 목록 대조 | - | ✅ DDL 파싱 필요 |
| API 명세 일치 | - | ✅ 코드 이해 필요 |
| 설계 근거 유효성 | - | ✅ 판단 필요 |

---

## 주의사항
- docs/ 내용을 함부로 삭제하지 않는다. 이력과 설계 근거는 보존한다.
- AGENTS.md 갱신 시 Wave 순서를 변경하지 않는다.
- 코드가 없는 Wave 3-5 항목은 "미완료"로 유지한다.
