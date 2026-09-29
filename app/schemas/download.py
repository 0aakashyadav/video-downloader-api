from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from app.core.config import settings


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=8, description="Video or audio URL to download")
    format: Literal["mp4", "mp3"] = "mp4"
    quality: Literal["360p", "480p", "720p", "1080p"] = "720p"

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        if value not in settings.ALLOWED_OUTPUT_FORMATS:
            raise ValueError(f"Unsupported format. Allowed: {settings.ALLOWED_OUTPUT_FORMATS}")
        return value

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, value: str) -> str:
        if value not in settings.ALLOWED_QUALITIES:
            raise ValueError(f"Unsupported quality. Allowed: {settings.ALLOWED_QUALITIES}")
        return value


class DownloadResponse(BaseModel):
    success: bool
    job_id: str
    status: str
    message: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    url: str
    status: str
    output_format: str
    quality: str
    progress: float
    download_url: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class FormatInfo(BaseModel):
    format_id: str | None = None
    ext: str | None = None
    resolution: str | None = None
    mime_type: str | None = None
    quality: str | None = None


class FormatsResponse(BaseModel):
    url: str
    title: str | None = None
    formats: list[FormatInfo]
