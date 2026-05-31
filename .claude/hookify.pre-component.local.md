---
name: pre-component
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: (components?|pages?).*\.tsx$
---

**[pre-component]** React 컴포넌트/페이지 파일 감지

`fe-review` skill 체크리스트 확인:

- [ ] `docs/01-requirements.md`에 해당 페이지/기능이 정의되어 있는가?
- [ ] 연결할 API 엔드포인트가 이미 구현되어 있는가? (없으면 API 먼저)
- [ ] TypeScript 타입이 `frontend/src/types/`에 정의되어 있는가?
- [ ] TypeScript `any` 타입 사용 금지
- [ ] 컴포넌트명: `PascalCase.tsx` / 훅명: `use + PascalCase.ts`
- [ ] API 클라이언트가 `frontend/src/api/`에 분리되어 있는가?
- [ ] shadcn/ui 컴포넌트 사용 시 설치 여부 확인 (`npx shadcn@latest add [component]`)
