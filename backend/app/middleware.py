import logging
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """요청/응답 로깅 + X-Request-Id / X-Process-Time 헤더 추가."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        logger.info("[%s] → %s %s", request_id, request.method, request.url.path)

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        logger.info("[%s] ← %d (%.2fms)", request_id, response.status_code, elapsed_ms)
        return response


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """전역 에러 핸들러 — HTTPException과 그 외 예외를 표준 ErrorResponse로 변환."""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                detail=str(exc.detail),
                code=f"HTTP_{exc.status_code}",
            ).model_dump(),
        )

    logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="내부 서버 오류가 발생했습니다.",
            code="INTERNAL_ERROR",
        ).model_dump(),
    )
