---
name: pre-db-change
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: (alembic|migrations|migration|\.sql)
---

**[pre-db-change]** DDL / 마이그레이션 파일 감지

작성 전 아래를 확인하라:

- [ ] `docs/02-erd-logical.md` — 변경 내용이 논리 ERD에 반영되어 있는가?
- [ ] `docs/03-erd-physical.md` — 물리 ERD에 반영되어 있는가?
- [ ] 새 테이블/컬럼이 ERD에 정의되어 있는가?
- [ ] 공통 컬럼 4개 포함: `id, created_at, updated_at, is_deleted`
- [ ] FK명 형식: `참조테이블_단수형_id`
- [ ] 인덱스명 형식: `idx_테이블_컬럼`
- [ ] 반정규화 적용 시 `docs/02-erd-logical.md`에 근거 기록 여부

미반영 항목 있으면 → **docs 먼저 수정 후 DDL 작성**
