"""계층적 청킹 모듈.

- 폰트 크기/굵기로 H1/H2/H3 제목 감지
- 섹션 경로(H1 > H2 > H3) 추적
- 300~500 토큰 목표, 50토큰 overlap
- 덤프 문제는 parse_dump_pages()로 별도 처리 (분리 금지)

docs/05-rag-pipeline.md 섹션 5-1 기준 구현.
"""
from __future__ import annotations

from dataclasses import dataclass

# 제목 감지 폰트 크기 임계값 (docs/05-rag-pipeline.md 섹션 5-1)
_H1_SIZE = 18.0
_H2_SIZE = 14.0
_H3_SIZE = 12.0

TARGET_TOKENS = 400
OVERLAP_TOKENS = 50
MIN_FLUSH_TOKENS = 100  # flush 최소 토큰 수 (너무 짧은 청크 방지)


@dataclass
class SectionPath:
    h1: str = ""
    h2: str = ""
    h3: str = ""

    def as_string(self) -> str:
        return " > ".join(p for p in [self.h1, self.h2, self.h3] if p)


def _estimate_tokens(text: str) -> int:
    """단어 수 기반 토큰 수 추정 (영어/한국어 혼합 기준, 1.3 계수)."""
    return max(1, int(len(text.split()) * 1.3))


def _detect_heading(block: dict) -> str | None:
    """폰트 크기와 굵기로 제목 레벨 감지. None이면 본문."""
    size: float = block.get("font_size", 0.0)
    bold: bool = block.get("is_bold", False)
    if size >= _H1_SIZE and bold:
        return "H1"
    if size >= _H2_SIZE and bold:
        return "H2"
    if size >= _H3_SIZE and bold:
        return "H3"
    return None


def hierarchical_chunk(
    pages: list[dict],
    document_version_id: str,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[dict]:
    """PDF 페이지 블록을 계층적으로 청킹한다.

    Args:
        pages: extract_text_blocks() 반환값
        document_version_id: DB document_versions.id (UUID 문자열)
        target_tokens: 목표 청크 토큰 수 (기본 400)
        overlap_tokens: 청크 간 overlap 토큰 수 (기본 50)

    Returns:
        [{"chunk_text": str, "chunk_order": int, "token_count": int,
          "section_path": str, "page_number": int,
          "document_version_id": str}]
    """
    chunks: list[dict] = []
    current_path = SectionPath()
    buffer: list[str] = []
    buf_tokens = 0
    chunk_order = 0
    current_page = 1

    def flush(page_num: int) -> None:
        nonlocal chunk_order, buf_tokens
        if not buffer:
            return
        text = " ".join(buffer)
        chunks.append({
            "chunk_text": text,
            "chunk_order": chunk_order,
            "token_count": buf_tokens,
            "section_path": current_path.as_string(),
            "page_number": page_num,
            "document_version_id": document_version_id,
        })
        chunk_order += 1

        # overlap: 마지막 3개 문장 유지 (약 50토큰)
        if len(buffer) > 3:
            buffer[:] = buffer[-3:]
            buf_tokens = overlap_tokens
        else:
            buffer.clear()
            buf_tokens = 0

    for page in pages:
        current_page = page["page"]
        for block in page["blocks"]:
            text: str = block.get("text", "").strip()
            if not text:
                continue

            level = _detect_heading(block)
            if level:
                # 새 섹션 시작 전 현재 버퍼 flush (최소 내용 있을 때만)
                if buf_tokens >= MIN_FLUSH_TOKENS:
                    flush(current_page)
                # 섹션 경로 업데이트
                if level == "H1":
                    current_path = SectionPath(h1=text)
                elif level == "H2":
                    current_path.h2 = text
                    current_path.h3 = ""
                elif level == "H3":
                    current_path.h3 = text
                continue

            est = _estimate_tokens(text)
            if buf_tokens + est > target_tokens and buf_tokens >= MIN_FLUSH_TOKENS:
                flush(current_page)

            buffer.append(text)
            buf_tokens += est

    # 마지막 버퍼 처리
    if buffer:
        flush(current_page)

    return chunks
