from __future__ import annotations
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.exam import router as exam_router
from app.api.practice import router as practice_router
from app.config import get_settings
from app.middleware import RequestLoggingMiddleware, global_exception_handler

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title="Passly API",
    version="0.1.0",
    description="자격증 문제풀이 플랫폼 API",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 요청 로깅 미들웨어
app.add_middleware(RequestLoggingMiddleware)

# 전역 에러 핸들러
app.add_exception_handler(Exception, global_exception_handler)

# 라우터
app.include_router(auth_router)
app.include_router(exam_router)
app.include_router(practice_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
