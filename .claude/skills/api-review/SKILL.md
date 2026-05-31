---
name: api-review
description: FastAPI 엔드포인트를 작성하거나 검토할 때 사용. pre-api Hook 트리거 시, 또는 review-agent가 API 코드를 검토할 때 호출.
version: 1.0.0
---

# Skill: FastAPI 엔드포인트 검토

## 사용 시점
- FastAPI 엔드포인트 작성/검토 시
- pre-api Hook이 이 파일을 지정했을 때
- review-agent가 API 코드 검토 시

---

## 엔드포인트 설계 기준

### 1. 표준 응답 구조
```python
# 성공 응답
{"data": ..., "message": "success"}

# 에러 응답
{"detail": "에러 메시지", "code": "ERROR_CODE"}
```

### 2. Pydantic 스키마 분리
```python
# schemas/exam.py
class ExamSessionCreate(BaseModel):
    certification_id: UUID
    exam_mode: str  # TIMED / PRACTICE / REVIEW
    question_count: int = 65

class ExamSessionResponse(BaseModel):
    id: UUID
    certification_id: UUID
    exam_mode: str
    total_questions: int
    created_at: datetime

    class Config:
        from_attributes = True
```

### 3. 에러 핸들링 패턴
```python
from fastapi import HTTPException

# 404
raise HTTPException(status_code=404, detail="Certification not found")

# 422 (유효성 검사는 Pydantic이 자동 처리)

# 500
raise HTTPException(status_code=500, detail="Internal server error")
```

### 4. 환경변수 사용
```python
# 절대 하드코딩 금지
DATABASE_URL = os.getenv("DATABASE_URL")  # 올바름
DATABASE_URL = "postgresql://..."          # 금지
```

### 5. 비동기 처리 (PDF 파이프라인)
PDF 파싱/임베딩은 시간이 걸리므로 백그라운드 태스크로 처리한다.
```python
from fastapi import BackgroundTasks

@router.post("/api/documents")
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks
):
    # 1. 파일 저장
    # 2. pipeline_runs 레코드 생성 (PENDING)
    # 3. 백그라운드 태스크 등록
    background_tasks.add_task(run_pipeline, document_id)
    return {"document_id": ..., "status": "PENDING"}
```

---

## 체크리스트
- [ ] 모든 엔드포인트에 Response 스키마가 명시되어 있는가?
- [ ] 에러 응답이 표준 형식을 따르는가?
- [ ] 환경변수가 하드코딩 없이 사용되는가?
- [ ] 긴 처리는 백그라운드 태스크로 분리되었는가?
- [ ] API 경로가 kebab-case인가?
- [ ] 인증이 필요한 엔드포인트에 의존성 주입이 있는가?
