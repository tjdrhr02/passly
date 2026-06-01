from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.models.certification import Certification
from app.models.user import User
from app.rag.generator import generate_answer
from app.rag.retriever import hybrid_search
from app.schemas.chat import ChatRequest, ChatResponse, SourceChunk
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=SuccessResponse[ChatResponse])
async def chat(
    body: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[ChatResponse]:
    # 1. 자격증 조회
    result = await db.execute(
        select(Certification).where(
            Certification.id == body.certification_id,
            Certification.is_active == True,  # noqa: E712
        )
    )
    certification = result.scalar_one_or_none()
    if certification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="자격증을 찾을 수 없습니다.",
        )

    # 2. 하이브리드 검색
    chunks = await hybrid_search(
        db,
        body.question,
        body.certification_id,
        user_access_level=current_user.access_level,
    )

    # 3. 답변 생성
    answer = await generate_answer(body.question, chunks, certification.name)

    # 4. 상위 3개 청크를 출처로 변환 (chunk_text 200자 truncate)
    sources = [
        SourceChunk(
            chunk_id=chunk["chunk_id"],
            chunk_text=chunk["chunk_text"][:200],
            rrf_score=chunk["rrf_score"],
        )
        for chunk in chunks[:3]
    ]

    return SuccessResponse(
        data=ChatResponse(answer=answer, sources=sources)
    )
