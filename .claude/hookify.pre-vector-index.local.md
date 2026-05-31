---
name: pre-vector-index
enabled: true
event: file
conditions:
  - field: new_text
    operator: regex_match
    pattern: (vector\(|IVFFlat|HNSW|chunk_embeddings|pgvector|<=>)
---

**[pre-vector-index]** pgvector 관련 코드 감지

`docs/04-vector-schema.md`를 읽었는가? (`pgvector-design` skill 참조)

필수 metadata 필드 포함 여부 확인:
- [ ] `chunk_id` (UUID, FK → document_chunks)
- [ ] `document_version_id` (UUID, FK)
- [ ] `certification_id` (UUID, FK — 자격증 필터링)
- [ ] `exam_domain_id` (UUID, FK — 영역 필터링)
- [ ] `topic_id` (UUID, FK — 개념 필터링)
- [ ] `difficulty` (VARCHAR)
- [ ] `access_level` (VARCHAR)
- [ ] `quality_score` (NUMERIC)
- [ ] `is_active` (BOOLEAN)
- [ ] `model_name` / `model_version`

인덱스 생성 시 → IVFFlat vs HNSW 선택 근거를 `docs/04-vector-schema.md`에 기록
