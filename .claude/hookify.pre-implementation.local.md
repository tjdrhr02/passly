---
name: pre-implementation
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.(py|ts|tsx)$
  - field: file_path
    operator: not_contains
    pattern: SKILL.md
---

**[pre-implementation]** 코드 파일 생성/수정 감지

작성 전 아래 체크리스트를 확인하라:

- [ ] 관련 `docs/` 파일이 존재하는가? (없으면 **중단하고 문서 먼저 작성**)
- [ ] ERD가 최신 상태인가?
- [ ] 명명 규칙 준수 (snake_case 테이블, kebab-case API, PascalCase 컴포넌트)
- [ ] 공통 컬럼 4개 기억: `id, created_at, updated_at, is_deleted`

관련 skill 확인:
- DB: `erd-review`, `normalization`
- pgvector: `pgvector-design`
- API: `api-review`
- 컴포넌트: `fe-review`
