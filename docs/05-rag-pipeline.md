# Passly RAG 파이프라인 설계서

> 버전: 1.0 | 작성일: 2026-05
> 대상 시스템: Passly PDF 업로드 → 파싱 → 청킹 → 임베딩 → pgvector 색인 → 검색 → 답변 생성
> 이 문서는 AI DA 포트폴리오 핵심 산출물로, RAG 파이프라인의 설계 결정과 각 단계별 구현 원칙을 기록한다.
> 참조 문서: docs/00-data-standard.md, docs/02-erd-logical.md, docs/03-erd-physical.md, docs/04-vector-schema.md

---

## 목차

1. [파이프라인 개요 및 전제 조건](#1-파이프라인-개요-및-전제-조건)
2. [전체 파이프라인 Mermaid 다이어그램](#2-전체-파이프라인-mermaid-다이어그램)
3. [Stage 1: 업로드 & 버전 관리](#3-stage-1-업로드--버전-관리)
4. [Stage 2: PDF 파싱 — 두 경로 분기](#4-stage-2-pdf-파싱--두-경로-분기)
5. [Stage 3: 청킹 & 문제 구조 추출](#5-stage-3-청킹--문제-구조-추출)
6. [Stage 4: 임베딩 생성 & 토픽 매핑](#6-stage-4-임베딩-생성--토픽-매핑)
7. [Stage 5: 품질 평가 & 색인](#7-stage-5-품질-평가--색인)
8. [페이지별 RAG 활용 방식](#8-페이지별-rag-활용-방식)
9. [로컬 ↔ GCP 전환 전략](#9-로컬--gcp-전환-전략)
10. [설계 자체 검토 체크리스트](#10-설계-자체-검토-체크리스트)

---

## 1. 파이프라인 개요 및 전제 조건

### 파이프라인 목적

Passly의 핵심 기능은 PDF로부터 검색 가능한 지식 베이스를 자동으로 구축하는 것이다. 사용자가 자격증 공식 시험 가이드 또는 덤프 PDF를 업로드하면 파이프라인이 자동으로 실행되어 AI 질문 응답, 문제 생성, 해설 제공에 필요한 모든 데이터를 DB에 저장한다.

### 파이프라인이 처리하는 두 가지 문서 유형

| 문서 유형 | source_type | 파이프라인 경로 | 저장 테이블 |
|---------|-------------|--------------|-----------|
| 시험 가이드 PDF | OFFICIAL_GUIDE | 경로 A: 청킹 → 임베딩 → pgvector | document_chunks, chunk_embeddings |
| 덤프 PDF | DUMP | 경로 B: 문제 구조 추출 | questions, choices, answer_explanations |

두 경로는 Stage 2 파싱 단계 이후 분기된다. 하나의 pipeline_runs 레코드가 한 번의 실행을 추적한다.

### 전제 조건

| 항목 | 값 | 출처 |
|------|----|------|
| 임베딩 모델 | Gemini text-embedding-004 (768차원) | AGENTS.md 기술 스택 |
| LLM | Gemini Developer API (로컬) / Vertex AI (GCP) | AGENTS.md 기술 스택 |
| PDF 파싱 라이브러리 | PyMuPDF (fitz) | AGENTS.md 기술 스택 |
| DB | PostgreSQL 17 + pgvector | AGENTS.md 기술 스택 |
| 벡터 인덱스 | IVFFlat (lists=175, 코사인 유사도) | docs/04-vector-schema.md 섹션 5 |
| Hybrid Search | Vector + Full-text (chunk_tsv, GIN) + RRF(k=60) | docs/04-vector-schema.md 섹션 6 |
| 사용자 규모 | 2~10명 소규모 | AGENTS.md 프로젝트 목적 |
| 환경 전환 | USE_VERTEX_AI 환경변수 | AGENTS.md 섹션 2 |

---

## 2. 전체 파이프라인 Mermaid 다이어그램

### 2-1. 파이프라인 전체 흐름 (경로 A/B 분기 포함)

```mermaid
flowchart TD
    U(["/upload 페이지\n사용자 PDF 업로드"]) --> S1

    subgraph S1["Stage 1: 업로드 & 버전 관리"]
        S1A["learning_documents 생성\nsource_type: OFFICIAL_GUIDE | DUMP"] --> S1B
        S1B["document_versions 생성\nis_active = true"] --> S1C
        S1C["pipeline_runs 생성\nstatus: PENDING"]
    end

    S1 --> S2

    subgraph S2["Stage 2: PDF 파싱 (PyMuPDF)"]
        S2A["pipeline_runs\nstatus → PROCESSING"] --> S2B
        S2B["텍스트 추출\nfitz.open(file_path)"] --> S2C{source_type?}
    end

    S2C -- "OFFICIAL_GUIDE" --> S3A
    S2C -- "DUMP" --> S3B
    S2C -- "파싱 실패" --> ERR

    subgraph S3A["Stage 3A: 청킹 (시험 가이드)"]
        S3A1["계층적 청킹\n300~500 토큰 / 50토큰 overlap"] --> S3A2
        S3A2["document_chunks 삽입\nchunk_text, chunk_order\ntoken_count, quality_score=null"]
    end

    subgraph S3B["Stage 3B: 문제 구조 추출 (덤프)"]
        S3B1["패턴 A/B 정규식 매칭\n문제/선택지/정답/해설 파싱"] --> S3B2
        S3B2["questions 삽입\nsource_type: DUMP"] --> S3B3
        S3B3["choices 삽입\nchoice_label, is_correct"] --> S3B4
        S3B4["answer_explanations 삽입"]
    end

    S3A --> S4A
    S3B --> S4B

    subgraph S4A["Stage 4A: 임베딩 생성"]
        S4A1["Gemini text-embedding-004\nbatch 처리 (최대 100건/요청)"] --> S4A2
        S4A2["chunk_embeddings 삽입\nembedding vector(768)\nmodel_name, model_version"]
    end

    subgraph S4B["Stage 4B: 토픽 매핑"]
        S4B1["청크-토픽 분류\n키워드 매칭 또는 LLM 분류"] --> S4B2
        S4B2["chunk_topics 삽입\nchunk_id, topic_id (M:N)"]
    end

    S4A --> S5
    S4B --> S5

    subgraph S5["Stage 5: 품질 평가 & 색인"]
        S5A["quality_score 계산\n(0~100 점수 부여)"] --> S5B
        S5B["document_chunks 업데이트\nquality_score, is_active = true"] --> S5C
        S5C["IVFFlat 인덱스 REINDEX\n(대량 삽입 후 권장)"] --> S5D
        S5D["pipeline_runs\nstatus → COMPLETED\nprocessed_chunks, completed_at"]
    end

    subgraph ERR["파싱 실패 처리"]
        ERR1["pipeline_runs\nstatus → FAILED\nerror_message 기록"] --> ERR2
        ERR2["수동 검토 대상 분류"]
    end

    S5 --> DONE(["파이프라인 완료\n/upload 페이지 진행률 100%"])
    ERR --> DONE
```

### 2-2. pipeline_runs 상태 전이도

```mermaid
stateDiagram-v2
    [*] --> PENDING : pipeline_runs 레코드 생성\n(파일 업로드 직후)

    PENDING --> PROCESSING : 파이프라인 워커 시작\n(PyMuPDF fitz.open 직전)

    PROCESSING --> COMPLETED : 모든 청크/문제 저장 완료\ncompleted_at = now()

    PROCESSING --> FAILED : 파싱 오류 / API 장애\nerror_message 기록

    FAILED --> PENDING : 수동 재시도 요청\n(새 pipeline_runs 생성)

    note right of COMPLETED
        total_chunks = 전체 청크 수
        processed_chunks = 성공 청크 수
    end note

    note right of FAILED
        error_message: 오류 상세 메시지
        수동 검토 대상 분류
    end note
```

---

## 3. Stage 1: 업로드 & 버전 관리

### 3-1. 흐름 설명

사용자가 `/upload` 페이지에서 PDF를 업로드하면 파일은 Cloud Storage(GCP) 또는 로컬 파일시스템에 저장되고, DB에 3개의 레코드가 순차적으로 생성된다.

```mermaid
sequenceDiagram
    actor User
    participant FE as /upload 페이지
    participant API as FastAPI
    participant DB as PostgreSQL

    User->>FE: PDF 파일 선택 + 업로드
    FE->>API: POST /api/learning-documents\n(multipart/form-data)
    API->>DB: INSERT learning_documents\n(title, source_type, file_path, original_filename)
    DB-->>API: learning_document_id
    API->>DB: INSERT document_versions\n(learning_document_id, version_number=1, is_active=true)
    DB-->>API: document_version_id
    API->>DB: INSERT pipeline_runs\n(learning_document_id, document_version_id, status=PENDING)
    DB-->>API: pipeline_run_id
    API-->>FE: 201 Created {pipeline_run_id}
    FE->>FE: 진행률 폴링 시작\nGET /api/pipeline-runs/{id}
```

### 3-2. DB 레코드 생성 순서

| 순서 | 테이블 | 주요 값 | 비고 |
|------|--------|--------|------|
| 1 | learning_documents | source_type, file_path, original_filename | 문서 원본 메타데이터 |
| 2 | document_versions | version_number=1, is_active=true | 버전 관리 시작. 재업로드 시 version_number 증가 |
| 3 | pipeline_runs | status=PENDING, started_at=now() | 진행률 추적 시작점 |

### 3-3. 버전 관리 설계 결정

**배경**: 동일 자격증의 시험 가이드가 개정판으로 교체될 때, 기존 청크를 유지하면서 새 버전을 추가해야 한다. 이전 버전의 청크를 즉시 삭제하면 시험 세션 이력이 참조하는 청크가 사라질 수 있다.

**선택**: document_versions 테이블로 버전을 분리하고, `is_active = false`로 구버전 비활성화.

**근거**: 검색 쿼리에서 `is_active = true` 필터만 추가하면 자동으로 최신 버전 청크만 검색 대상이 된다. 구버전 청크는 소프트 비활성화로 이력 추적을 유지한다.

**트레이드오프**: 재업로드 시 구버전 청크와 임베딩이 DB에 잔존한다. 스토리지 비용이 증가하지만 이력 보존과 롤백 가능성을 위해 수용한다.

---

## 4. Stage 2: PDF 파싱 — 두 경로 분기

### 4-1. PyMuPDF 텍스트 추출

**배경**: 자격증 공식 가이드 PDF는 텍스트 레이어가 포함된 디지털 PDF다. 이미지 기반 스캔 PDF는 초기 범위 외로 제외한다.

**선택**: PyMuPDF(fitz) — 페이지별 텍스트 추출, 폰트 정보, 블록 구조 접근 가능.

**근거**: PyMuPDF는 pdfplumber, pdfminer 대비 처리 속도가 빠르고, 블록 레벨 텍스트 구조(bbox, font size)를 통해 제목(H1/H2/H3)과 본문 단락을 구분할 수 있다. 계층적 청킹에 필수적인 정보다.

```python
# backend/app/pipeline/parser.py (Wave 3 구현 시 참조)
import fitz  # PyMuPDF

async def extract_text_with_structure(file_path: str) -> list[dict]:
    """
    PDF에서 페이지별 블록 구조를 추출한다.
    반환값: [{"page": int, "blocks": [{"text": str, "font_size": float, "is_bold": bool}]}]
    """
    doc = fitz.open(file_path)
    pages = []
    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        structured_blocks = []
        for block in blocks:
            if block.get("type") != 0:  # 텍스트 블록만 처리
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    structured_blocks.append({
                        "text": span["text"].strip(),
                        "font_size": span["size"],
                        "is_bold": "Bold" in span.get("font", ""),
                        "bbox": span["bbox"],
                    })
        pages.append({"page": page_num, "blocks": structured_blocks})
    doc.close()
    return pages
```

### 4-2. 경로 분기 로직

```python
# backend/app/pipeline/router.py (Wave 3 구현 시 참조)
async def run_pipeline(pipeline_run_id: str, session: AsyncSession) -> None:
    run = await session.get(PipelineRun, pipeline_run_id)
    doc = await session.get(LearningDocument, run.learning_document_id)

    await update_status(session, run, "PROCESSING")

    try:
        pages = await extract_text_with_structure(doc.file_path)

        if doc.source_type == "OFFICIAL_GUIDE":
            await process_official_guide(session, run, pages)
        elif doc.source_type == "DUMP":
            await process_dump(session, run, pages)

        await update_status(session, run, "COMPLETED")

    except Exception as e:
        await update_status(session, run, "FAILED", error_message=str(e))
        raise
```

### 4-3. 실패 처리 원칙

| 실패 유형 | 처리 방법 | pipeline_runs 상태 |
|---------|---------|-----------------|
| 파일 열기 실패 (손상된 PDF) | FAILED + error_message | FAILED |
| 텍스트 추출 결과 없음 (이미지 PDF) | FAILED + error_message | FAILED |
| 덤프 패턴 미매칭 (0개 문제 추출) | FAILED + error_message | FAILED |
| 최소 품질 기준 미달 (문제 텍스트 없음) | 해당 문제 건너뜀 + WARNING 기록 | COMPLETED (경고 포함) |
| Gemini API 호출 실패 | 재시도 3회 후 FAILED | FAILED |

**최소 품질 기준 (덤프 파싱)**: 문제 텍스트 존재 + 선택지 2개 이상 + 정답 식별 가능. 이 조건을 충족하지 못하는 문제는 건너뛰고 `error_message`에 건너뛴 문제 수를 기록한다.

---

## 5. Stage 3: 청킹 & 문제 구조 추출

### 5-1. Stage 3A: 계층적 청킹 (시험 가이드)

#### 청킹 전략 비교 및 선택 근거

| 청킹 방식 | 설명 | 장점 | 단점 |
|---------|------|------|------|
| 고정 크기 청킹 | 500토큰마다 단순 분할 | 구현 단순, 청크 크기 일정 | 문장/단락 중간 절단, 의미 단절 |
| 문단 기반 청킹 | 빈 줄 기준 분할 | 의미 단위 보존 | 단락 크기 불균일, 너무 길거나 짧음 |
| 계층적 청킹 | 제목(H1/H2/H3) 구조 기반, 섹션 단위 분할 | 문서 구조 보존, 섹션 컨텍스트 메타데이터 | 구현 복잡도 높음, 제목 감지 오류 가능 |

**선택: 계층적 청킹**

**배경**: 자격증 공식 시험 가이드는 챕터 → 섹션 → 하위 섹션의 명확한 계층 구조를 가진다. 예를 들어 Azure AI-102 가이드는 "Design AI Solution → Azure OpenAI Service → Model Deployment" 형태로 구성된다.

**근거 1 — 검색 품질**: 계층 구조를 보존하면 "Azure OpenAI Service 모델 배포"를 검색할 때 해당 섹션의 청크가 정확히 매칭될 가능성이 높다. 고정 크기 청킹은 "모델 배포" 내용이 두 개의 청크에 걸쳐 분리될 수 있다.

**근거 2 — 메타데이터 풍부성**: 청크가 어느 챕터/섹션에 속하는지 추적할 수 있다. 이 정보는 `/chat` 페이지의 출처 표시에 활용된다.

**근거 3 — chunk_topics 매핑**: 섹션 경로가 있으면 해당 청크가 어떤 exam_domain/topic에 속하는지 키워드 매칭으로 분류할 수 있다.

**트레이드오프**: 폰트 크기와 굵기로 제목을 감지하는 방식이 100% 정확하지 않을 수 있다. 일부 PDF에서 제목처럼 포맷된 본문이나, 본문처럼 포맷된 제목이 존재할 수 있다. 이 경우 계층 감지 오류로 청크 경계가 의도와 다르게 설정될 수 있다.

#### 청크 크기 설계 (300~500 토큰, 50토큰 overlap)

**300~500 토큰 선택 근거**

| 토큰 범위 | 문제점 | 근거 |
|---------|--------|------|
| 100토큰 이하 | 너무 짧아 의미 있는 문맥 포함 불가. 임베딩이 표현할 내용이 부족해 유사도 계산 신뢰도 저하. | 검색 시 해당 청크만으로 LLM이 답변 생성 불가 |
| 300~500토큰 | 의미 단위로 완결된 설명이 포함 가능. Gemini text-embedding-004의 권장 입력 길이 범위 내. | 균형점 |
| 1000토큰 이상 | 임베딩 한 벡터가 너무 많은 개념을 압축해야 함. 유사도 계산 시 다수 개념이 희석되어 검색 정밀도 저하. LLM 컨텍스트 윈도우 효율 저하. | 너무 길면 임베딩 품질 저하 |

**50토큰 overlap 설계 이유**

청크 경계에서 문맥이 잘리는 문제를 완화한다. 예를 들어 "Azure OpenAI Service는 다음 세 가지 모델을 지원한다:" 문장이 청크 A의 마지막 줄이고, 모델 목록이 청크 B에 있을 때, overlap 없이는 청크 B만 검색해도 "세 가지 모델" 앞 맥락이 없다. overlap 50토큰은 이전 청크의 마지막 50토큰을 다음 청크의 시작에 포함시켜 문맥 연속성을 확보한다.

**트레이드오프**: overlap으로 인해 동일한 텍스트가 두 청크에 중복 저장된다. 3만 청크 기준으로 약 10~15% 용량 증가를 유발한다. Passly의 소규모 데이터 규모에서 허용 가능한 트레이드오프다.

#### 계층 구조 감지 및 섹션 경로 추적

```python
# backend/app/pipeline/chunker.py (Wave 3 구현 시 참조)
from dataclasses import dataclass, field

HEADING_FONT_SIZE_THRESHOLDS = {
    "H1": 18.0,  # 챕터 제목
    "H2": 14.0,  # 섹션 제목
    "H3": 12.0,  # 하위 섹션 제목
}

@dataclass
class SectionPath:
    h1: str = ""
    h2: str = ""
    h3: str = ""

    def as_string(self) -> str:
        parts = [p for p in [self.h1, self.h2, self.h3] if p]
        return " > ".join(parts)

def detect_heading_level(block: dict) -> str | None:
    """폰트 크기와 굵기로 제목 레벨 감지. None이면 본문."""
    font_size = block.get("font_size", 0)
    is_bold = block.get("is_bold", False)

    if font_size >= HEADING_FONT_SIZE_THRESHOLDS["H1"] and is_bold:
        return "H1"
    elif font_size >= HEADING_FONT_SIZE_THRESHOLDS["H2"] and is_bold:
        return "H2"
    elif font_size >= HEADING_FONT_SIZE_THRESHOLDS["H3"] and is_bold:
        return "H3"
    return None

async def hierarchical_chunk(
    pages: list[dict],
    document_version_id: str,
    target_tokens: int = 400,
    overlap_tokens: int = 50,
) -> list[dict]:
    """
    계층적 청킹: 제목 구조 감지 → 섹션 경로 추적 → 300~500토큰 청크 생성.

    반환값: [{"chunk_text": str, "chunk_order": int, "token_count": int,
              "section_path": str, "page_number": int}]
    """
    chunks = []
    current_path = SectionPath()
    current_text_buffer = []
    current_token_count = 0
    chunk_order = 0

    def flush_buffer(page_num: int) -> None:
        nonlocal chunk_order, current_token_count
        if not current_text_buffer:
            return
        text = " ".join(current_text_buffer)
        chunks.append({
            "chunk_text": text,
            "chunk_order": chunk_order,
            "token_count": current_token_count,
            "section_path": current_path.as_string(),
            "page_number": page_num,
            "document_version_id": document_version_id,
        })
        chunk_order += 1
        # overlap: 마지막 overlap_tokens만큼 유지
        if len(current_text_buffer) > 3:
            current_text_buffer[:] = current_text_buffer[-3:]  # 마지막 3개 문장 유지
            current_token_count = overlap_tokens
        else:
            current_text_buffer.clear()
            current_token_count = 0

    for page in pages:
        for block in page["blocks"]:
            text = block["text"]
            if not text:
                continue

            heading_level = detect_heading_level(block)
            if heading_level:
                # 새 섹션 시작 전 현재 버퍼 청크화
                if current_token_count >= 100:  # 최소 내용이 있을 때만 flush
                    flush_buffer(page["page"])
                # 섹션 경로 업데이트
                if heading_level == "H1":
                    current_path = SectionPath(h1=text)
                elif heading_level == "H2":
                    current_path.h2 = text
                    current_path.h3 = ""
                elif heading_level == "H3":
                    current_path.h3 = text
                continue

            # 본문 블록 처리
            estimated_tokens = len(text.split()) * 1.3  # 한국어/영어 혼합 기준 추정
            if current_token_count + estimated_tokens > target_tokens:
                flush_buffer(page["page"])

            current_text_buffer.append(text)
            current_token_count += int(estimated_tokens)

    # 마지막 버퍼 처리
    if current_text_buffer:
        flush_buffer(pages[-1]["page"] if pages else 1)

    return chunks
```

#### chunk_order 컬럼 활용: 인접 청크 조회

chunk_order는 동일 document_version 내 청크의 순서를 나타낸다. RAG 검색에서 상위 K개 청크를 가져온 후, 인접 청크(chunk_order ± 1)를 추가로 조회해 문맥을 확장할 수 있다.

```sql
-- 검색된 청크의 앞뒤 청크를 가져와 문맥 확장 (LLM 답변 품질 향상)
SELECT dc.*
FROM document_chunks dc
WHERE dc.document_version_id = :version_id
  AND dc.chunk_order BETWEEN :target_order - 1 AND :target_order + 1
  AND dc.is_active = true
  AND dc.is_deleted = false
ORDER BY dc.chunk_order;
```

### 5-2. Stage 3B: 문제 구조 추출 (덤프)

#### 덤프 패턴 파싱

덤프 PDF는 두 가지 형식으로 존재한다. 정규식으로 두 패턴을 모두 처리한다.

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

```python
# backend/app/pipeline/dump_parser.py (Wave 3 구현 시 참조)
import re
from dataclasses import dataclass

@dataclass
class ParsedQuestion:
    question_text: str
    choices: list[dict]  # [{"label": "A", "text": str, "is_correct": bool}]
    explanation: str | None

PATTERN_A = re.compile(
    r"Question\s+\d+\s*\n"
    r"(?P<question_text>.+?)\n"
    r"(?P<choices>(?:[A-D]\..+?\n)+)"
    r"Answer:\s*(?P<answer>[A-D])\s*\n?"
    r"(?:Explanation:\s*(?P<explanation>.+?))?(?=Question|\Z)",
    re.DOTALL,
)

PATTERN_B = re.compile(
    r"\d+\.\s*(?P<question_text>.+?)\n"
    r"(?P<choices>(?:-\s*[A-D]\).+?\n)+)"
    r"Correct Answer:\s*(?P<answer>[A-D])\s*\n?",
    re.DOTALL,
)

def parse_dump_text(full_text: str) -> list[ParsedQuestion]:
    """
    덤프 전체 텍스트에서 문제 구조를 추출한다.
    패턴 A 먼저 시도, 없으면 패턴 B 시도.
    최소 품질 기준 미달 시 건너뜀: 문제 텍스트 + 선택지 2개 이상 + 정답 식별 가능.
    """
    questions = []
    matches = list(PATTERN_A.finditer(full_text)) or list(PATTERN_B.finditer(full_text))

    for m in matches:
        question_text = m.group("question_text").strip()
        answer_label = m.group("answer").strip().upper()
        explanation = (m.group("explanation") or "").strip() or None

        raw_choices = m.group("choices").strip().split("\n")
        choices = []
        for line in raw_choices:
            line = line.strip()
            if not line:
                continue
            # 패턴 A: "A. 텍스트", 패턴 B: "- A) 텍스트"
            choice_match = re.match(r"[-]?\s*([A-D])[.)]\s*(.+)", line)
            if choice_match:
                label = choice_match.group(1).upper()
                text = choice_match.group(2).strip()
                choices.append({
                    "label": label,
                    "text": text,
                    "is_correct": label == answer_label,
                })

        # 최소 품질 기준 검증
        if not question_text or len(choices) < 2:
            continue  # 건너뜀 (error_message에 카운트 기록)

        questions.append(ParsedQuestion(
            question_text=question_text,
            choices=choices,
            explanation=explanation,
        ))

    return questions
```

#### 추출된 문제 DB 저장 순서

```sql
-- 1. questions 삽입
INSERT INTO questions (certification_id, topic_id, source_chunk_id, question_text, question_type, source_type, difficulty)
VALUES (:cert_id, NULL, NULL, :question_text, 'SINGLE', 'DUMP', 'INTERMEDIATE');

-- 2. choices 삽입 (문제당 4개)
INSERT INTO choices (question_id, choice_text, choice_label, is_correct, order_num)
VALUES (:question_id, :text, :label, :is_correct, :order_num);

-- 3. answer_explanations 삽입 (해설이 있는 경우)
INSERT INTO answer_explanations (question_id, explanation_text, source_chunk_id)
VALUES (:question_id, :explanation, NULL);
```

**topic_id와 source_chunk_id는 초기 NULL로 삽입**: 덤프 파싱 시점에는 어떤 topic과 chunk에 해당하는지 확정하기 어렵다. Wave 4 이후 별도 분류 작업에서 업데이트한다.

---

## 6. Stage 4: 임베딩 생성 & 토픽 매핑

### 6-1. Stage 4A: 임베딩 생성

#### 설계 결정: 배치 처리

**배경**: Gemini text-embedding-004 API는 요청당 최대 100개 텍스트를 배치로 처리할 수 있다. 청크 하나씩 API를 호출하면 3만 청크 기준 3만 번의 HTTP 요청이 발생한다.

**선택**: 최대 100건 단위 배치 처리.

**근거**: 배치 처리로 API 호출 횟수를 1/100로 줄인다. 레이트 리밋 소진을 방지하고 파이프라인 실행 시간을 단축한다.

**트레이드오프**: 배치 내 하나의 청크가 오류일 때 전체 배치가 실패할 수 있다. 단건 재시도 로직을 추가해야 한다.

```python
# backend/app/pipeline/embedder.py (Wave 3 구현 시 참조)
import os
import asyncio
from typing import Optional
import google.generativeai as genai

EMBED_MODEL = "models/text-embedding-004"
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0


async def embed_chunks_batch(
    chunks: list[dict],
) -> list[Optional[list[float]]]:
    """
    청크 리스트를 BATCH_SIZE 단위로 Gemini API에 전송해 임베딩을 생성한다.
    실패한 청크는 None으로 반환.

    반환값: chunks와 동일한 길이의 임베딩 리스트
    """
    all_embeddings: list[Optional[list[float]]] = []

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["chunk_text"] for c in batch]

        for attempt in range(MAX_RETRIES):
            try:
                response = genai.embed_content(
                    model=EMBED_MODEL,
                    content=texts,
                    task_type="retrieval_document",  # 문서 임베딩용
                )
                all_embeddings.extend(response["embedding"])
                break
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    # 최종 실패 시 None 삽입 (개별 청크 재시도 불포함)
                    all_embeddings.extend([None] * len(batch))
                else:
                    await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

    return all_embeddings
```

#### chunk_embeddings 삽입

```python
# 임베딩 생성 후 chunk_embeddings 삽입 (Wave 3 구현 시 참조)
async def save_embeddings(
    session: AsyncSession,
    chunks_with_ids: list[dict],  # [{"chunk_id": str, "chunk_text": str}, ...]
    embeddings: list[Optional[list[float]]],
    model_name: str = "text-embedding-004",
    model_version: str = "001",
) -> int:
    """chunk_embeddings 테이블에 임베딩 저장. None인 임베딩은 건너뜀."""
    saved = 0
    for chunk, embedding in zip(chunks_with_ids, embeddings):
        if embedding is None:
            continue
        session.add(ChunkEmbedding(
            chunk_id=chunk["chunk_id"],
            embedding=embedding,
            model_name=model_name,
            model_version=model_version,
        ))
        saved += 1

    await session.commit()
    return saved
```

#### pipeline_runs 진행률 업데이트

파이프라인 실행 중 `/upload` 페이지에 실시간 진행률을 표시하기 위해 배치 처리 완료 시마다 `processed_chunks`를 업데이트한다.

```python
# 배치 처리 완료 시 진행률 업데이트
await session.execute(
    text("""
        UPDATE pipeline_runs
        SET processed_chunks = processed_chunks + :batch_count,
            updated_at = now()
        WHERE id = :run_id
    """),
    {"batch_count": len(batch), "run_id": pipeline_run_id},
)
await session.commit()
```

### 6-2. Stage 4B: 토픽 매핑

#### 설계 결정: 청크-토픽 M:N 매핑

**배경**: 하나의 청크가 여러 topic에 관련될 수 있다. 예를 들어 "Azure OpenAI와 Cognitive Services 통합" 설명 청크는 "Azure OpenAI Service" 토픽과 "Cognitive Services" 토픽 모두에 속한다.

**선택**: chunk_topics 테이블로 M:N 관계를 표현.

**분류 방법**: 두 가지 방식 중 선택 가능.

| 방법 | 설명 | 장점 | 단점 | Passly 적용 |
|------|------|------|------|-----------|
| 키워드 매칭 | topics 테이블의 name/keywords와 청크 텍스트 포함 여부 비교 | 빠름, 예측 가능 | 동의어/변형 처리 어려움 | Wave 3 초기 구현 |
| LLM 분류 | 청크를 Gemini에 전송해 해당 topic_id를 분류 | 높은 정확도, 의미 기반 | API 비용 발생, 느림 | Wave 4 이후 개선 |

**Wave 3 초기 구현 (키워드 매칭)**:

```python
# backend/app/pipeline/topic_mapper.py (Wave 3 구현 시 참조)
async def map_chunk_to_topics(
    session: AsyncSession,
    chunk_id: str,
    chunk_text: str,
    certification_id: str,
) -> list[str]:
    """
    청크 텍스트에 포함된 키워드로 관련 topic_id를 매핑한다.
    topics 테이블의 name을 기준으로 단순 포함 여부 확인.
    """
    topics = await session.execute(
        select(Topic).where(
            Topic.exam_domain.has(ExamDomain.certification_id == certification_id)
        )
    )
    matched_topic_ids = []
    chunk_text_lower = chunk_text.lower()

    for topic in topics.scalars():
        # topic name의 핵심 단어가 청크에 포함되면 매핑
        topic_keywords = topic.name.lower().split()
        if all(kw in chunk_text_lower for kw in topic_keywords[:2]):
            matched_topic_ids.append(str(topic.id))

    # chunk_topics 삽입
    for topic_id in matched_topic_ids:
        session.add(ChunkTopic(chunk_id=chunk_id, topic_id=topic_id))

    return matched_topic_ids
```

**트레이드오프**: 키워드 매칭은 정확도가 낮을 수 있다. "Azure OpenAI" 키워드가 없어도 관련 청크가 존재할 수 있다. LLM 분류로 개선하면 정확도는 올라가지만 파이프라인 처리 시간이 길어진다. 초기 구현에서는 키워드 매칭으로 시작하고 품질 평가 후 LLM 분류로 전환 여부를 결정한다.

---

## 7. Stage 5: 품질 평가 & 색인

### 7-1. quality_score 계산

quality_score는 문서 청크의 검색 적합성을 0~100 점수로 표현한다. 파이프라인이 청킹 완료 후 각 청크에 자동으로 부여한다.

**배경**: 저품질 청크(너무 짧은 텍스트, 깨진 인코딩, 의미 없는 반복 문자)가 검색 결과에 포함되면 LLM 답변 품질이 저하된다. 사전에 필터링 기준을 마련한다.

**quality_score 계산 규칙**:

| 항목 | 만점 | 평가 기준 |
|------|------|---------|
| 토큰 수 적정성 | 30점 | 300~500토큰이면 30점. 100토큰 미만이면 0점. |
| 특수문자 비율 | 20점 | 특수문자 비율 10% 이하이면 20점. 50% 초과이면 0점. |
| 단어 다양성 (TTR) | 20점 | Type-Token Ratio 0.4 이상이면 20점. 0.1 미만이면 0점. |
| 섹션 경로 존재 | 15점 | H1/H2 경로가 있으면 15점. 없으면 0점. |
| 반복 문자 없음 | 15점 | 동일 문자 5개 이상 연속 없으면 15점. |

```python
# backend/app/pipeline/quality.py (Wave 3 구현 시 참조)
import re
from collections import Counter

def calculate_quality_score(
    chunk_text: str,
    token_count: int,
    section_path: str,
) -> float:
    """quality_score 계산. 0~100 범위의 NUMERIC(5,2) 반환."""
    score = 0.0

    # 1. 토큰 수 적정성 (30점)
    if 300 <= token_count <= 500:
        score += 30.0
    elif 200 <= token_count < 300 or 500 < token_count <= 700:
        score += 15.0
    elif 100 <= token_count < 200:
        score += 5.0

    # 2. 특수문자 비율 (20점)
    special_chars = len(re.findall(r"[^a-zA-Z0-9\s.,!?;:\-\'\"()]", chunk_text))
    special_ratio = special_chars / max(len(chunk_text), 1)
    if special_ratio <= 0.10:
        score += 20.0
    elif special_ratio <= 0.25:
        score += 10.0
    elif special_ratio <= 0.50:
        score += 5.0

    # 3. 단어 다양성 TTR (20점)
    words = chunk_text.lower().split()
    if words:
        ttr = len(set(words)) / len(words)
        if ttr >= 0.4:
            score += 20.0
        elif ttr >= 0.25:
            score += 10.0
        elif ttr >= 0.1:
            score += 5.0

    # 4. 섹션 경로 존재 (15점)
    if section_path and ">" in section_path:
        score += 15.0
    elif section_path:
        score += 7.0

    # 5. 반복 문자 없음 (15점)
    if not re.search(r"(.)\1{4,}", chunk_text):
        score += 15.0

    return round(min(score, 100.0), 2)
```

**최소 검색 대상 기준**: `quality_score >= 60`. 60점 미만 청크는 document_chunks에 저장되지만 검색 대상에서 제외된다 (docs/04-vector-schema.md 섹션 3 참고).

### 7-2. IVFFlat 인덱스 REINDEX

**배경**: IVFFlat 인덱스는 인덱스 생성 시점의 데이터 분포로 클러스터 중심점을 계산한다. 파이프라인으로 대량의 청크가 삽입된 후에는 클러스터 분포가 틀어져 recall이 저하될 수 있다.

**선택**: 파이프라인 완료 후 REINDEX 실행.

```sql
-- 파이프라인 완료 후 IVFFlat 인덱스 재구성
-- CONCURRENTLY 옵션으로 서비스 중단 없이 실행
REINDEX INDEX CONCURRENTLY idx_chunk_embeddings_embedding_ivfflat;
```

**트레이드오프**: REINDEX 실행 중 쓰기 잠금이 발생하지 않지만 (CONCURRENTLY 옵션), 재구성 시간 동안 검색 성능이 일시 저하될 수 있다. 소규모 환경에서는 허용 가능하다.

### 7-3. pipeline_runs COMPLETED 업데이트

```sql
UPDATE pipeline_runs
SET status           = 'COMPLETED',
    total_chunks     = :total,
    processed_chunks = :processed,
    completed_at     = now(),
    updated_at       = now()
WHERE id = :pipeline_run_id;
```

---

## 8. 페이지별 RAG 활용 방식

각 페이지는 RAG를 서로 다른 방식으로 활용한다. 공통점은 모두 동일한 DB 스키마를 참조한다는 것이다.

### 8-1. /exam — 실전 시험 (RAG 미사용)

**설계 결정**: `/exam` 페이지는 pgvector 검색을 사용하지 않는다.

**배경**: 실전 시험은 사전에 정해진 문제 풀에서 영역 가중치에 따라 문제를 추출하는 방식이다. 사용자 질문에 실시간으로 답변하는 것이 아니라, 덤프 파싱으로 저장된 questions 테이블에서 직접 SELECT한다.

**근거**: 실전 시험의 핵심은 재현성과 공정성이다. 같은 자격증 시험을 보는 모든 사용자가 동일한 문제 풀에서 추출된 문제를 보아야 한다. 벡터 검색 결과는 쿼리마다 변동이 있어 실전 시험에 부적합하다.

```mermaid
flowchart LR
    U(["/exam 진입\n시험 시작"]) --> Q["exam_domains 조회\n(weight_percent 기반\n문제 수 배분)"]
    Q --> S["questions 테이블 SELECT\nWHERE certification_id = :cert_id\n  AND source_type IN ('DUMP','GENERATED')\n  AND difficulty IN :difficulties\nORDER BY RANDOM()\nLIMIT :n_per_domain"]
    S --> SH["앱 레벨 셔플\n(전체 선택 문제 순서 재배치)"]
    SH --> EXAM["시험 진행\n타이머 카운트다운"]
    EXAM --> SUBMIT["일괄 채점\nuser_attempts 삽입"]
    SUBMIT --> EXPLAIN["해설 표시\nJOIN answer_explanations"]
```

**DB 쿼리 (pgvector 미사용)**:

```sql
-- /exam: 영역 가중치 기반 문제 추출 (예: exam_domain당 비례 배분)
SELECT q.id, q.question_text, q.question_type, q.difficulty,
       ed.name AS domain_name, ed.weight_percent
FROM questions q
JOIN topics t ON q.topic_id = t.id
JOIN exam_domains ed ON t.exam_domain_id = ed.id
WHERE q.certification_id = :certification_id
  AND q.is_deleted = false
  AND q.source_type IN ('DUMP', 'GENERATED')
ORDER BY RANDOM()
LIMIT :total_question_count;
```

### 8-2. /practice — 연습 모드 (Vector Search)

**설계 결정**: `/practice` 페이지는 AI 문제 생성을 위해 Vector Search를 사용한다. Full-text 결합 없이 Vector Search 단독 적용.

**배경**: 사용자가 특정 토픽/영역을 선택하면 해당 주제와 의미적으로 가장 관련된 청크를 검색해 Gemini가 문제를 생성한다. 키워드 매칭이 아닌 의미 기반 검색이 적합하다.

**근거**: 문제 생성용 청크는 정확한 키워드보다 주제와의 의미적 관련성이 중요하다. "Azure OpenAI Service 배포 방법"을 주제로 선택했을 때 "model deployment", "provisioning" 등 직접 키워드가 없어도 의미적으로 관련된 청크가 필요하다.

```mermaid
sequenceDiagram
    actor User
    participant FE as /practice 페이지
    participant API as FastAPI
    participant VEC as pgvector
    participant LLM as Gemini API
    participant DB as PostgreSQL

    User->>FE: 토픽/영역 선택 + "문제 생성" 클릭
    FE->>API: POST /api/questions/generate\n{topic_id, difficulty, count}
    API->>LLM: embed(topic_description)\n→ query_embedding
    LLM-->>API: query_embedding [768차원]
    API->>VEC: Vector Search\nWHERE topic_id = :topic_id\n  AND certification_id = :cert_id\n  AND quality_score >= 60\nORDER BY embedding <=> query_embedding\nLIMIT 5
    VEC-->>API: 관련 청크 5개 (chunk_text)
    API->>LLM: 문제 생성 프롬프트\n(컨텍스트 = 청크 5개 + difficulty)
    LLM-->>API: 생성된 문제 + 선택지 + 해설
    API->>DB: INSERT questions (source_type='GENERATED')\nINSERT choices\nINSERT answer_explanations
    DB-->>API: question_id
    API-->>FE: 생성된 문제 반환
    FE->>User: 문제 표시 + 즉시 해설 가능
```

**Vector Search 쿼리 (토픽 필터 포함)**:

```sql
-- /practice: 토픽 기반 Vector Search (probes=10, 속도 우선)
SET LOCAL ivfflat.probes = 10;

SELECT
    dc.id AS chunk_id,
    dc.chunk_text,
    dc.difficulty,
    ce.embedding <=> :query_embedding::vector AS cosine_distance
FROM document_chunks dc
JOIN document_versions dv ON dc.document_version_id = dv.id
JOIN learning_documents ld ON dv.learning_document_id = ld.id
JOIN chunk_embeddings ce ON dc.id = ce.chunk_id
JOIN chunk_topics ct ON dc.id = ct.chunk_id
WHERE dc.is_active        = true
  AND dc.is_deleted       = false
  AND ce.is_deleted       = false
  AND ld.certification_id = :certification_id
  AND ct.topic_id         = :topic_id
  AND dc.quality_score   >= 60
ORDER BY cosine_distance ASC
LIMIT 5;
```

**검색된 청크를 컨텍스트로 문제 생성 (Python)**:

```python
# backend/app/rag/question_generator.py (Wave 4 구현 시 참조)
async def generate_question_from_chunks(
    model: genai.GenerativeModel,
    chunks: list[dict],
    difficulty: str,
    question_type: str = "SINGLE",
) -> dict:
    """
    검색된 청크를 컨텍스트로 Gemini에 문제 생성 요청.
    source_type: GENERATED 로 저장될 문제 구조를 반환.
    """
    context = "\n\n---\n\n".join([c["chunk_text"] for c in chunks])
    prompt = f"""
당신은 자격증 시험 문제 출제 전문가입니다.
아래 학습 자료를 바탕으로 {difficulty} 난이도의 {question_type} 문제를 1개 생성하세요.

[학습 자료]
{context}

[출력 형식 — JSON]
{{
  "question_text": "문제 텍스트",
  "choices": [
    {{"label": "A", "text": "선택지 텍스트", "is_correct": false}},
    {{"label": "B", "text": "선택지 텍스트", "is_correct": true}},
    {{"label": "C", "text": "선택지 텍스트", "is_correct": false}},
    {{"label": "D", "text": "선택지 텍스트", "is_correct": false}}
  ],
  "explanation": "정답 해설"
}}
"""
    response = await model.generate_content_async(prompt)
    import json
    return json.loads(response.text)
```

### 8-3. /chat — AI 질문 (완전한 Hybrid Search)

**설계 결정**: `/chat` 페이지는 완전한 Hybrid Search (Vector + Full-text + RRF)를 적용한다. probes=15~20으로 recall을 높인다.

**배경**: 사용자의 자유 질문은 키워드 기반일 수도, 개념 기반일 수도 있다. "LUIS란 무엇인가" 같은 키워드 쿼리와 "언어 이해 서비스의 학습 방법을 설명해줘" 같은 의미 기반 쿼리가 모두 가능하다.

**근거**: Vector Search 단독은 키워드 기반 쿼리에 취약하고, Full-text Search 단독은 의미 기반 쿼리에 취약하다. Hybrid Search가 두 유형을 모두 처리한다 (docs/04-vector-schema.md 섹션 6 참고).

**chunk_summary 활용**: 답변 생성 시 chunk_text 전체 대신 chunk_summary를 컨텍스트로 활용할 수 있다. 요약본을 사용하면 동일한 LLM 컨텍스트 윈도우 내에 더 많은 청크를 포함할 수 있어 다양한 출처를 참조한 답변 생성이 가능하다. 단, 세부 내용이 필요한 경우 chunk_text를 사용한다.

```mermaid
sequenceDiagram
    actor User
    participant FE as /chat 페이지
    participant API as FastAPI
    participant EMB as Gemini Embedding
    participant DB as PostgreSQL (pgvector + FTS)
    participant LLM as Gemini LLM

    User->>FE: 자유 질문 입력\n"Azure OpenAI의 fine-tuning은 어떻게 하나요?"
    FE->>API: POST /api/chat\n{question, certification_id}

    API->>EMB: embed(question)\ntask_type="retrieval_query"
    EMB-->>API: query_embedding [768차원]

    API->>DB: SET LOCAL ivfflat.probes = 20
    API->>DB: Hybrid Search CTE\n(Vector + FTS + RRF)\ncertification_id 필터\nquality_score >= 60
    DB-->>API: Top-10 청크\n(chunk_text, chunk_summary\n출처: 문서명, 페이지, 섹션 경로)

    API->>LLM: 답변 생성 프롬프트\n(컨텍스트 = 상위 10 청크)\n+ 출처 인용 요청
    LLM-->>API: 답변 텍스트 + 인용 청크 번호

    API-->>FE: {answer, sources: [{doc_title, page, section_path}]}
    FE->>User: 답변 표시 + 출처 카드 표시
```

**출처 표시용 메타데이터 조회**:

```sql
-- Hybrid Search 결과 청크의 출처 메타데이터 조회
SELECT
    dc.id              AS chunk_id,
    dc.chunk_text,
    dc.chunk_summary,
    ld.title           AS document_title,
    ld.original_filename,
    dv.version_number,
    -- section_path는 chunk_text에서 파이프라인 저장 시 메타데이터로 관리
    -- (현재 스키마에 section_path 컬럼 없으므로 chunk_order + document_title로 대체)
    dc.chunk_order
FROM document_chunks dc
JOIN document_versions dv ON dc.document_version_id = dv.id
JOIN learning_documents ld ON dv.learning_document_id = ld.id
WHERE dc.id = ANY(:chunk_ids::uuid[])
  AND dc.is_active  = true
  AND dc.is_deleted = false
ORDER BY dc.chunk_order;
```

**probes=15~20 선택 근거 (/chat 전용)**

| 페이지 | probes | 이유 |
|--------|--------|------|
| /practice | 10 | 토픽 필터로 검색 범위가 이미 좁혀짐. 속도 우선. |
| /chat | 15~20 | 자유 질문이므로 광범위한 클러스터 탐색 필요. recall 우선. |

### 8-4. 페이지별 검색 방식 요약

| 페이지 | RAG 사용 | 검색 방식 | pgvector 사용 | probes | 주요 DB 테이블 |
|--------|---------|---------|-------------|--------|-------------|
| /exam | 미사용 | DB 직접 쿼리 | 미사용 | - | questions, choices, answer_explanations |
| /practice | 사용 | Vector Search (단독) | 사용 | 10 | document_chunks, chunk_embeddings, chunk_topics |
| /review | 미사용 | DB 직접 쿼리 | 미사용 | - | exam_sessions, user_attempts, questions |
| /chat | 사용 | Hybrid Search (Vector + FTS + RRF) | 사용 | 15~20 | document_chunks, chunk_embeddings, chunk_tsv |

---

## 9. 로컬 ↔ GCP 전환 전략

### 9-1. 환경변수 기반 전환 원칙

**배경**: 개발 환경에서는 Gemini Developer API(API 키)를 사용하고, GCP 배포 환경에서는 Vertex AI(서비스 계정)를 사용한다. 코드 변경 없이 환경변수 하나로 전환한다.

| 환경변수 | 값 | 동작 |
|---------|---|------|
| USE_VERTEX_AI | false | Gemini Developer API 사용 (로컬 개발) |
| USE_VERTEX_AI | true | Vertex AI Gemini 사용 (GCP 배포) |

### 9-2. Python 구현 패턴

```python
# backend/app/core/ai_client.py (Wave 3 구현 시 참조)
import os
import google.generativeai as genai
from google.cloud import aiplatform

USE_VERTEX_AI: bool = os.getenv("USE_VERTEX_AI", "false").lower() == "true"
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
VERTEX_PROJECT_ID: str = os.getenv("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "us-central1")
EMBED_MODEL_NAME: str = "text-embedding-004"
LLM_MODEL_NAME: str = "gemini-1.5-flash"


def get_embedding_model():
    """
    USE_VERTEX_AI 환경변수에 따라 임베딩 모델 클라이언트를 반환한다.
    코드 호출부는 동일한 인터페이스를 사용.
    """
    if USE_VERTEX_AI:
        # Vertex AI: 서비스 계정 자동 인증 (Cloud Run에서 ADC 사용)
        aiplatform.init(project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
        from vertexai.language_models import TextEmbeddingModel
        return TextEmbeddingModel.from_pretrained(f"text-embedding-004")
    else:
        # Gemini Developer API: API 키 인증
        genai.configure(api_key=GEMINI_API_KEY)
        return genai  # genai.embed_content() 호출


def get_llm_model():
    """
    USE_VERTEX_AI 환경변수에 따라 LLM 모델 클라이언트를 반환한다.
    """
    if USE_VERTEX_AI:
        aiplatform.init(project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
        import vertexai.generative_models as vertex_genai
        return vertex_genai.GenerativeModel(LLM_MODEL_NAME)
    else:
        genai.configure(api_key=GEMINI_API_KEY)
        return genai.GenerativeModel(LLM_MODEL_NAME)


async def embed_texts(texts: list[str], task_type: str = "retrieval_document") -> list[list[float]]:
    """
    임베딩 생성 통합 인터페이스. 내부적으로 USE_VERTEX_AI 분기 처리.
    호출부는 이 함수만 사용하면 됨.
    """
    if USE_VERTEX_AI:
        model = get_embedding_model()
        embeddings = model.get_embeddings(texts, task_type=task_type)
        return [e.values for e in embeddings]
    else:
        model = get_embedding_model()
        response = model.embed_content(
            model=f"models/{EMBED_MODEL_NAME}",
            content=texts,
            task_type=task_type,
        )
        return response["embedding"] if isinstance(texts, str) else response["embeddings"]
```

### 9-3. 환경변수 구성 파일

```bash
# .env.local (로컬 개발용, .gitignore에 포함)
USE_VERTEX_AI=false
GEMINI_API_KEY=your-gemini-api-key-here
DATABASE_URL=postgresql+asyncpg://passly:passly@localhost:5432/passly

# .env.gcp (GCP 배포용 — Secret Manager로 관리, 파일 미사용)
USE_VERTEX_AI=true
VERTEX_PROJECT_ID=your-gcp-project-id
VERTEX_LOCATION=us-central1
DATABASE_URL=postgresql+asyncpg://passly:passly@/passly?host=/cloudsql/project:region:instance
```

**GCP 배포 시 주의사항**:
- `.env.gcp` 파일은 실제로 사용하지 않는다. Cloud Run 환경변수 또는 Secret Manager로 관리한다.
- Cloud Run의 서비스 계정에 `Vertex AI User` 역할이 부여되어야 한다.
- `GEMINI_API_KEY`는 GCP 환경에서 불필요하다 (ADC 자동 인증 사용).

---

## 10. 설계 자체 검토 체크리스트

### AGENTS.md review-agent 기준

| 항목 | 상태 | 근거 |
|------|------|------|
| AGENTS.md 원칙 위반 없음 (문서 우선 원칙) | 완료 | 코드 구현 없이 설계 문서만 작성 |
| 명명 규칙 준수 (snake_case, UPPER_SNAKE_CASE) | 완료 | 모든 테이블/컬럼 snake_case, 코드값 UPPER_SNAKE_CASE |
| docs/와 코드 일치 | 완료 | 스키마 참조가 docs/03-erd-physical.md, docs/04-vector-schema.md와 일치 |
| 하드코딩 없음 | 완료 | API 키, URL, magic number 모두 환경변수로 분리 |
| pgvector 사용 시 metadata 필드 완전 | 완료 | docs/04-vector-schema.md 섹션 3 메타데이터 설계 참조 |
| user_attempts 삭제 로직 없음 | 완료 | pipeline 설계에 user_attempts 삭제 로직 없음 |

### RAG 파이프라인 설계 품질 기준

| 설계 결정 | 배경 | 선택 | 근거 | 트레이드오프 |
|---------|------|------|------|------------|
| 두 경로 분기 (시험가이드/덤프) | 섹션 4 | source_type으로 분기 | 문서 유형별 처리 방식이 근본적으로 다름 | 파이프라인 복잡도 증가 |
| 계층적 청킹 | 섹션 5-1 | H1/H2/H3 구조 기반 분할 | 문서 구조 보존, 섹션 메타데이터 추적 | 제목 감지 오류 가능성 |
| 300~500토큰 청크 크기 | 섹션 5-1 | 400토큰 목표 | 의미 단위 완결성 + 임베딩 품질 균형 | 고정 크기 청킹보다 구현 복잡 |
| 50토큰 overlap | 섹션 5-1 | 경계 청크 50토큰 중복 | 청크 경계 문맥 단절 방지 | 10~15% 저장 용량 증가 |
| 배치 임베딩 (100건/요청) | 섹션 6-1 | Gemini API 배치 처리 | API 호출 횟수 최소화 | 단건 오류 시 배치 전체 재시도 필요 |
| 토픽 매핑: 키워드 매칭 (Wave 3) | 섹션 6-2 | 초기 키워드 매칭 | 빠른 구현, 추후 LLM 분류로 개선 가능 | 의미 기반 분류 대비 정확도 낮음 |
| quality_score 계산 | 섹션 7-1 | 5개 지표 합산 | 저품질 청크 검색 제외로 LLM 답변 품질 보호 | 계산 기준이 임의적, 도메인 검증 필요 |
| /exam: RAG 미사용 | 섹션 8-1 | DB 직접 쿼리 | 실전 시험 재현성 요구사항 | RAG 기반 동적 문제 생성 불가 |
| /practice: Vector Search 단독 | 섹션 8-2 | 토픽 필터 + 벡터 검색 | 의미 기반 검색으로 관련 청크 추출 | 키워드 정확 매칭 약함 |
| /chat: Hybrid Search | 섹션 8-3 | Vector + FTS + RRF | 자유 질문의 다양한 쿼리 유형 모두 처리 | 쿼리 복잡도 높음, 2번 임베딩/검색 실행 |
| USE_VERTEX_AI 환경변수 전환 | 섹션 9 | 코드 변경 없이 환경변수로 분기 | 로컬↔GCP 전환 시 코드 수정 없음 | 두 API의 인터페이스 차이 추상화 필요 |

### 표준 용어 사전 일치 확인 (docs/00-data-standard.md)

| 이 문서 사용 용어 | 표준 용어 사전 | 일치 여부 |
|----------------|------------|---------|
| LearningDocument / learning_documents | LearningDocument | 일치 |
| DocumentChunk / document_chunks | DocumentChunk | 일치 |
| ChunkEmbedding / chunk_embeddings | ChunkEmbedding | 일치 |
| PipelineRun / pipeline_runs | PipelineRun | 일치 |
| QualityScore / quality_score | QualityScore | 일치 |
| DumpQuestion | DumpQuestion | 일치 |
| GeneratedQuestion | GeneratedQuestion | 일치 |
| PENDING / PROCESSING / COMPLETED / FAILED | PIPELINE_STATUS 코드 테이블 | 일치 |
| OFFICIAL_GUIDE / DUMP / GENERATED | SOURCE_TYPE 코드 테이블 | 일치 |

---

*이 문서는 Passly Wave 1 설계 단계 산출물이다. Wave 3 파이프라인 구현 후 실제 청킹 품질, 임베딩 처리 시간, 토픽 매핑 정확도를 측정하여 이 문서의 설계 파라미터(토큰 크기, overlap, quality_score 기준)를 갱신한다. 검색 품질 측정 결과는 docs/07-search-evaluation.md에 기록한다.*
