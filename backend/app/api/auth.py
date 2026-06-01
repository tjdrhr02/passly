"""인증 API 라우터.

POST /api/auth/register — 회원 가입
POST /api/auth/login    — 로그인 (JWT 발급)
get_current_user       — JWT 검증 의존성 (다른 라우터에서 Depends로 사용)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_access_token, hash_password
from app.dependencies import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """JWT 토큰에서 현재 사용자를 반환하는 의존성."""
    auth_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 토큰이 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise auth_exc
    except JWTError:
        raise auth_exc

    result = await db.execute(
        select(User).where(
            User.id == uuid.UUID(user_id),
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise auth_exc
    return user


@router.post(
    "/register",
    response_model=SuccessResponse[AuthResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[AuthResponse]:
    # 이메일 중복 확인
    existing = await db.execute(
        select(User).where(User.email == body.email, User.is_deleted == False)  # noqa: E712
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )

    hashed_pw = hash_password(body.password)
    user = User(
        email=body.email,
        name=body.name,
        access_level="SHARED",
    )
    # TODO: User 모델에 hashed_password 컬럼 추가 후 저장 (Wave 4에서 확정)
    # 현재는 인증 흐름 구조만 구성, 실제 비밀번호 검증은 Wave 4 완성
    _ = hashed_pw  # noqa: F841
    db.add(user)
    await db.flush()

    token = create_access_token(str(user.id), {"email": user.email})
    await db.commit()

    return SuccessResponse(
        data=AuthResponse(
            access_token=token,
            user_id=str(user.id),
            email=user.email,
            name=user.name,
        )
    )


@router.post("/login", response_model=SuccessResponse[AuthResponse])
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[AuthResponse]:
    result = await db.execute(
        select(User).where(User.email == body.email, User.is_deleted == False)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    # TODO: verify_password(body.password, user.hashed_password) — Wave 4에서 완성

    token = create_access_token(str(user.id), {"email": user.email})
    return SuccessResponse(
        data=AuthResponse(
            access_token=token,
            user_id=str(user.id),
            email=user.email,
            name=user.name,
        )
    )
