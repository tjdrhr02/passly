---
name: pre-api
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: (routers?|api|endpoints?).*\.py$
---

**[pre-api]** FastAPI 엔드포인트 파일 감지

`api-review` skill 체크리스트 확인:

- [ ] `docs/01-requirements.md`에서 해당 기능 요구사항 확인했는가?
- [ ] Request/Response Pydantic 스키마가 `schemas/`에 정의되어 있는가?
- [ ] 에러 응답 형식: `{"detail": "...", "code": "ERROR_CODE"}`
- [ ] 인증/권한 처리가 고려됐는가?
- [ ] 하드코딩 없음 (환경변수로 분리)
- [ ] API 경로가 kebab-case인가? (`/api/exam-sessions`)
- [ ] 관련 DB 테이블이 이미 DDL로 구현되어 있는가? (없으면 Wave 2 먼저)
