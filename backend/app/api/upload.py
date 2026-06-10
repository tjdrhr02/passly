"""업로드 API 라우터.

POST /api/upload             — PDF 업로드 + 파이프라인 Run 생성
GET  /api/upload/certifications — 자격증 목록
GET  /api/upload/history     — 업로드 이력 (페이지네이션)
GET  /api/upload/{run_id}/status — 파이프라인 진행 상태 폴링
"""
from __future__ import annotations

import os
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.models.certification import Certification
from app.models.document_version import DocumentVersion
from app.models.learning_document import LearningDocument
from app.models.pipeline_run import PipelineRun
from app.models.user import User
from app.pipeline.pipeline import run_pipeline
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.upload import CertificationOut, DocumentOut, PipelineRunOut, UploadResponse

router = APIRouter(prefix="/api/upload", tags=["upload"])

_ALLOWED_MIME = {"application/pdf"}
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.get(
    "/certifications",
    response_model=SuccessResponse[list[CertificationOut]],
)
async def list_certifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[list[CertificationOut]]:
    """활성 자격증 목록을 반환한다."""
    result = await db.execute(
        select(Certification).where(
            Certification.is_active == True,  # noqa: E712
            Certification.is_deleted == False,  # noqa: E712
        ).order_by(Certification.name)
    )
    certs = result.scalars().all()
    return SuccessResponse(data=[CertificationOut.model_validate(c) for c in certs])


@router.post(
    "",
    response_model=SuccessResponse[UploadResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(description="업로드할 PDF 파일")],
    certification_id: Annotated[uuid.UUID, Form(description="자격증 ID")],
    source_type: Annotated[str, Form(description="OFFICIAL_GUIDE 또는 DUMP")],
    title: Annotated[str, Form(description="문서 제목")],
) -> SuccessResponse[UploadResponse]:
    """PDF 파일을 업로드하고 파이프라인 Run을 생성한다."""
    # 파일 검증
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF 파일만 업로드 가능합니다.",
        )

    content = await file.read()
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="파일 크기는 100MB를 초과할 수 없습니다.",
        )

    # source_type 검증
    if source_type not in ("OFFICIAL_GUIDE", "DUMP"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_type은 OFFICIAL_GUIDE 또는 DUMP 이어야 합니다.",
        )

    # 자격증 존재 확인
    cert_result = await db.execute(
        select(Certification).where(
            Certification.id == certification_id,
            Certification.is_active == True,  # noqa: E712
            Certification.is_deleted == False,  # noqa: E712
        )
    )
    if cert_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="존재하지 않는 자격증입니다.",
        )

    # 파일을 /tmp에 저장 (BackgroundTask가 같은 프로세스에서 실행되므로 접근 가능)
    # doc.id 기반 디렉터리로 파일명 충돌 방지
    from app.config import get_settings as _get_settings
    _settings = _get_settings()
    _upload_tmp = getattr(_settings, "upload_tmp_dir", "/tmp/passly/uploads")
    safe_filename = file.filename or "upload.pdf"
    # doc 생성 전이므로 임시 UUID 디렉터리 사용, 이후 doc.id로 file_path 갱신
    _tmp_uuid = str(uuid.uuid4())
    tmp_dir = f"{_upload_tmp}/{_tmp_uuid}"
    os.makedirs(tmp_dir, exist_ok=True)
    file_path = f"{tmp_dir}/{safe_filename}"
    with open(file_path, "wb") as f_out:
        f_out.write(content)

    doc = LearningDocument(
        certification_id=certification_id,
        title=title,
        source_type=source_type,
        file_path=file_path,
        original_filename=file.filename or "upload.pdf",
        is_active=True,
    )
    db.add(doc)
    await db.flush()

    # OFFICIAL_GUIDE의 경우 document_version 생성
    dv: DocumentVersion | None = None
    if source_type == "OFFICIAL_GUIDE":
        dv = DocumentVersion(
            learning_document_id=doc.id,
            version_number=1,
            is_active=True,
        )
        db.add(dv)
        await db.flush()

    run = PipelineRun(
        learning_document_id=doc.id,
        document_version_id=dv.id if dv else None,
        status="PENDING",
        processed_chunks=0,
    )
    db.add(run)
    await db.flush()
    await db.commit()

    # 파이프라인을 백그라운드에서 실행
    background_tasks.add_task(run_pipeline, run.id)

    return SuccessResponse(
        data=UploadResponse(
            document=DocumentOut.model_validate(doc),
            pipeline_run=PipelineRunOut.model_validate(run),
        )
    )


@router.get(
    "/history",
    response_model=PaginatedResponse[DocumentOut],
)
async def upload_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[DocumentOut]:
    """업로드된 문서 이력을 반환한다."""
    offset = (page - 1) * page_size

    count_result = await db.execute(
        select(func.count()).select_from(LearningDocument).where(
            LearningDocument.is_deleted == False  # noqa: E712
        )
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(LearningDocument)
        .where(LearningDocument.is_deleted == False)  # noqa: E712
        .order_by(LearningDocument.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    docs = result.scalars().all()

    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[DocumentOut.model_validate(d) for d in docs],
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


@router.delete(
    "/{doc_id}",
    response_model=SuccessResponse[None],
)
async def delete_document(
    doc_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[None]:
    """업로드된 문서와 관련 파이프라인 Run을 소프트 삭제한다."""
    result = await db.execute(
        select(LearningDocument).where(
            LearningDocument.id == doc_id,
            LearningDocument.is_deleted == False,  # noqa: E712
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="문서를 찾을 수 없습니다.",
        )

    # 소프트 삭제: learning_document + 연관 pipeline_runs
    from sqlalchemy import update as sa_update
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    await db.execute(
        sa_update(LearningDocument)
        .where(LearningDocument.id == doc_id)
        .values(is_deleted=True, updated_at=now)
    )
    await db.execute(
        sa_update(PipelineRun)
        .where(PipelineRun.learning_document_id == doc_id)
        .values(is_deleted=True, updated_at=now)
    )
    await db.commit()
    return SuccessResponse(data=None, message="삭제되었습니다.")


@router.get(
    "/{run_id}/status",
    response_model=SuccessResponse[PipelineRunOut],
)
async def pipeline_run_status(
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[PipelineRunOut]:
    """파이프라인 Run의 진행 상태를 반환한다."""
    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.id == run_id,
            PipelineRun.is_deleted == False,  # noqa: E712
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="파이프라인 Run을 찾을 수 없습니다.",
        )
    return SuccessResponse(data=PipelineRunOut.model_validate(run))
