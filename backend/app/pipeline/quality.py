"""청크 품질 점수 계산 모듈.

docs/06-data-quality.md 섹션 1 기준 5개 지표 합산 (최대 100점):
  [1] 토큰 수 적정성   30점
  [2] 텍스트 다양성    25점  (unique_chars / total_chars)
  [3] 구조 완결성      20점  (문장 완결 비율)
  [4] 인코딩 안정성    15점  (U+FFFD 비율)
  [5] 섹션 경로 존재   10점
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ChunkQualityInput:
    chunk_text: str
    token_count: int
    section_path: str  # SectionPath.as_string() 결과


def compute_quality_score(chunk: ChunkQualityInput) -> float:
    """quality_score 계산 (0.00~100.00). document_chunks.quality_score 컬럼에 저장."""
    score = 0.0
    text = chunk.chunk_text

    # [1] 토큰 수 적정성 (30점)
    t = chunk.token_count
    if 300 <= t <= 500:
        score += 30.0
    elif (100 <= t < 300) or (500 < t <= 700):
        score += 15.0

    # [2] 텍스트 다양성 (25점): unique_chars / total_chars
    if len(text) > 0:
        ratio = len(set(text)) / len(text)
        if ratio >= 0.3:
            score += min(ratio * 25.0, 25.0)

    # [3] 구조 완결성 (20점): 마침표/물음표로 끝나는 문장 비율
    sentences = re.split(r"(?<=[.?!])\s", text)
    if sentences:
        complete = sum(1 for s in sentences if s.strip().endswith((".", "?")))
        score += min((complete / len(sentences)) * 20.0, 20.0)

    # [4] 인코딩 안정성 (15점): U+FFFD (replacement char) 비율
    repl_count = text.count("�")
    if repl_count == 0:
        score += 15.0
    elif len(text) > 0 and repl_count / len(text) < 0.01:
        score += 8.0

    # [5] 섹션 경로 존재 (10점)
    if chunk.section_path:
        score += 10.0

    return round(min(score, 100.0), 2)


def resolve_is_active(quality_score: float) -> bool:
    """60점 미만이면 검색 대상 제외 (is_active=false)."""
    return quality_score >= 60.0
