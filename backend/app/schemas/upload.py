"""업로드 관련 Pydantic 스키마."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CertificationOut(BaseModel):
    id: uuid.UUID
    name: str
    vendor: str
    exam_code: str

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: uuid.UUID
    certification_id: uuid.UUID
    title: str
    source_type: str
    original_filename: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunOut(BaseModel):
    id: uuid.UUID
    learning_document_id: uuid.UUID
    document_version_id: Optional[uuid.UUID]
    status: str
    total_chunks: Optional[int]
    processed_chunks: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    document: DocumentOut
    pipeline_run: PipelineRunOut
