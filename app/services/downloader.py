from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import DownloadJob, DownloadedFile
from app.schemas.download import DownloadRequest, DownloadResponse, FormatsResponse, FormatInfo, JobStatusResponse
from app.services.downloader import downloader_service

router = APIRouter(prefix=settings.API_V1_PREFIX, tags=["downloads"])


@router.get("/formats")
async def get_supported_formats(url: str = Query(..., description="URL to inspect")) -> FormatsResponse:
    result = await downloader_service.get_available_formats(url)
    mapped_formats = [
        FormatInfo(
            format_id=item.get("format_id"),
            ext=item.get("ext"),
            resolution=item.get("resolution"),
            mime_type=item.get("mime_type"),
            quality=item.get("quality"),
        )
        for item in result["formats"]
    ]
    return FormatsResponse(url=result["url"], title=result["title"], formats=mapped_formats)


@router.post("/download", response_model=DownloadResponse)
async def create_download(payload: DownloadRequest, db: Session = Depends(get_db)) -> DownloadResponse:
    if not downloader_service.is_valid_url(payload.url):
        raise HTTPException(status_code=400, detail="URL is invalid or unsupported")

    job = downloader_service.create_job(db, payload.url, payload.format, payload.quality)
    asyncio.create_task(downloader_service.process_job(job.id))
    return DownloadResponse(success=True, job_id=job.id, status="processing", message="Download job created successfully")


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.id,
        url=job.url,
        status=job.status,
        output_format=job.output_format,
        quality=job.quality,
        progress=job.progress,
        download_url=job.download_url,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get("/files/{file_id}")
async def serve_file(file_id: str, db: Session = Depends(get_db)) -> FileResponse:
    file_record = db.query(DownloadedFile).filter(DownloadedFile.id == file_id).one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_record.storage_path, media_type=file_record.mime_type, filename=file_record.file_name)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: str, db: Session = Depends(get_db)) -> Response:
    file_record = db.query(DownloadedFile).filter(DownloadedFile.id == file_id).one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    import os
    if os.path.exists(file_record.storage_path):
        os.remove(file_record.storage_path)

    db.delete(file_record)
    db.commit()
    return Response(status_code=204)
