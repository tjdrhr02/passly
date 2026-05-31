---
name: pdf-parsing
description: PDF 파싱 로직을 구현하거나 검토할 때 사용. backend/app/pipeline/parser.py 작성 시 또는 파싱 전략을 설계할 때 호출.
version: 1.0.0
---

# Skill: PDF 파싱 전략

## 사용 시점
- backend/app/pipeline/parser.py 구현 시
- PDF 파싱 로직 설계/검토 시

---

## 덤프 PDF 파싱 전략

### 파싱 대상
1. 시험 가이드 PDF → 학습 문서 청크 (RAG용)
2. 덤프 PDF → 문제/선택지/정답/해설 구조 추출

### 덤프 파싱 패턴 (PyMuPDF)
덤프 PDF는 보통 아래 형식 중 하나다:
```
패턴 A:
Question 1
문제 텍스트...
A. 선택지1
B. 선택지2
C. 선택지3
D. 선택지4
Answer: B
Explanation: 해설...

패턴 B:
1. 문제 텍스트
- A) 선택지1
- B) 선택지2
Correct Answer: A
```

### 파싱 구현 원칙
```python
import fitz  # PyMuPDF

def parse_dump_pdf(file_path: str) -> list[dict]:
    doc = fitz.open(file_path)
    questions = []

    for page in doc:
        text = page.get_text()
        # 패턴 매칭으로 문제 블록 추출
        # ...

    return questions
```

### 파싱 품질 관리
- 파싱 성공률을 pipeline_runs 테이블에 기록
- 파싱 실패 문제는 FAILED 상태로 표시하고 수동 검토 대상으로 분류
- 최소 품질 기준: 문제 텍스트 + 선택지 2개 이상 + 정답 식별 가능

### 시험 가이드 청킹 전략
```
청킹 방식: 계층적 청킹
  문서 → 챕터 → 섹션 → 문단 단위

청크 크기: 300~500 토큰 (Gemini 기준)
청크 중복: 50토큰 overlap (문맥 연속성 확보)
청크 메타데이터: 제목, 페이지 번호, 섹션 경로
```

---

## 체크리스트
- [ ] 파싱 실패 케이스를 pipeline_runs에 기록하는가?
- [ ] 품질 점수가 파싱 완료 시 계산되는가?
- [ ] 청크 크기가 300~500 토큰 범위인가?
- [ ] 청크에 topic_id가 연결되는가?
- [ ] 파싱 결과가 document_chunks에 저장되는가?
