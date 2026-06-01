"""PDF 파싱 모듈.

OFFICIAL_GUIDE: 페이지별 텍스트 블록 구조 추출 (계층적 청킹 입력용)
DUMP: 정규식 패턴 A/B로 문제/선택지/정답/해설 구조 파싱

docs/05-rag-pipeline.md 섹션 4 기준 구현.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import fitz  # PyMuPDF


# ──────────────────────────────────────────────
# OFFICIAL_GUIDE 파싱
# ──────────────────────────────────────────────

def extract_text_blocks(file_path: str) -> list[dict]:
    """PDF에서 페이지별 텍스트 블록 구조를 추출한다.

    Returns:
        [{"page": int, "blocks": [{"text": str, "font_size": float, "is_bold": bool}]}]

    Raises:
        RuntimeError: 파일 열기 실패 (손상, 암호화)
        ValueError: 텍스트 레이어 없음 (이미지 PDF) 또는 빈 문서
    """
    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        raise RuntimeError(f"PDF 파일 열기 실패: {file_path} — {exc}") from exc

    if doc.page_count == 0:
        doc.close()
        raise ValueError(f"빈 문서: {file_path}")

    pages: list[dict] = []
    total_text_len = 0

    for page_num, page in enumerate(doc, start=1):
        raw = page.get_text("dict")
        blocks_out: list[dict] = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:  # 텍스트 블록만 처리
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    blocks_out.append({
                        "text": text,
                        "font_size": span.get("size", 0.0),
                        "is_bold": "Bold" in span.get("font", ""),
                        "bbox": span.get("bbox", ()),
                    })
                    total_text_len += len(text)

        pages.append({"page": page_num, "blocks": blocks_out})

    doc.close()

    if total_text_len == 0:
        raise ValueError(
            f"텍스트 레이어 없음 (이미지 PDF 가능성): {file_path}"
        )

    return pages


# ──────────────────────────────────────────────
# DUMP 파싱
# ──────────────────────────────────────────────

@dataclass
class ParsedQuestion:
    question_text: str
    choices: list[dict]  # [{"label": str, "text": str, "is_correct": bool, "order_num": int}]
    explanation: str | None = None


# 패턴 A: "Question N\n문제\nA. 선택지\nAnswer: B\nExplanation: ..."
_PATTERN_A = re.compile(
    r"Question\s+\d+\s*\n"
    r"(?P<question_text>.+?)\n"
    r"(?P<choices>(?:[A-D]\..+?\n)+)"
    r"Answer:\s*(?P<answer>[A-D])\s*\n?"
    r"(?:Explanation:\s*(?P<explanation>.+?))?(?=Question\s+\d+|\Z)",
    re.DOTALL,
)

# 패턴 B: "N. 문제\n- A) 선택지\nCorrect Answer: A"
_PATTERN_B = re.compile(
    r"\d+\.\s*(?P<question_text>.+?)\n"
    r"(?P<choices>(?:[-\s]*[A-D][).].+?\n)+)"
    r"(?:Correct Answer|Answer):\s*(?P<answer>[A-D])\s*\n?",
    re.DOTALL,
)

_CHOICE_RE_A = re.compile(r"^([A-D])\.\s*(.+)$")
_CHOICE_RE_B = re.compile(r"^[-\s]*([A-D])[).]\s*(.+)$")


def _parse_choices(raw: str, answer: str, pattern_key: str) -> list[dict]:
    regex = _CHOICE_RE_A if pattern_key == "A" else _CHOICE_RE_B
    choices = []
    for i, line in enumerate(raw.strip().splitlines()):
        line = line.strip()
        m = regex.match(line)
        if not m:
            continue
        label = m.group(1).upper()
        choices.append({
            "label": label,
            "text": m.group(2).strip(),
            "is_correct": label == answer.upper(),
            "order_num": i,
        })
    return choices


def parse_dump_pages(pages: list[dict]) -> list[ParsedQuestion]:
    """페이지 블록에서 덤프 문제 구조를 추출한다.

    최소 품질 기준: 문제 텍스트 존재 + 선택지 2개 이상 + 정답 식별 가능.
    기준 미달 문제는 건너뛴다 (docs/05-rag-pipeline.md 섹션 4-3).

    Raises:
        ValueError: 패턴 A/B 모두 0개 매칭 (덤프 형식 불일치)
    """
    full_text = "\n".join(
        block["text"]
        for page in pages
        for block in page["blocks"]
    )

    matches_a = list(_PATTERN_A.finditer(full_text))
    matches_b = list(_PATTERN_B.finditer(full_text))

    if not matches_a and not matches_b:
        raise ValueError(
            "덤프 패턴 매칭 실패: 패턴 A/B 모두 0개 문제 추출. "
            "다른 덤프 형식이거나 OFFICIAL_GUIDE로 업로드해야 합니다."
        )

    matches, pat_key = (
        (matches_a, "A") if len(matches_a) >= len(matches_b) else (matches_b, "B")
    )

    questions: list[ParsedQuestion] = []
    for m in matches:
        q_text = m.group("question_text").strip()
        answer = m.group("answer").strip().upper()
        exp_raw = m.group("explanation") if "explanation" in m.groupdict() else None
        explanation = exp_raw.strip() if exp_raw else None

        choices = _parse_choices(m.group("choices"), answer, pat_key)

        # 최소 품질 기준 검증
        if not q_text or len(choices) < 2:
            continue

        questions.append(ParsedQuestion(
            question_text=q_text,
            choices=choices,
            explanation=explanation,
        ))

    return questions
