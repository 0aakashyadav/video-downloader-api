from __future__ import annotations

import asyncio
import mimetypes
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal, ensure_storage_dir
from app.db.models import DownloadJob, DownloadedFile


class DownloaderService:
    def __init__(self) -> None:
        self.storage_dir = ensure_storage_dir()

    @staticmethod
    def is_valid_url(url: str) -> bool:
        parsed = urlparse(url)
        return bool(parsed.scheme in {"http", "https"} and parsed.netloc)

    @staticmethod
    def sanitize_name(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
        return cleaned or "download"

    def quality_to_height(self, quality: str) -> int:
        mapping = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080}
        return mapping.get(quality, 720)

    async def get_available_formats(self, url: str) -> dict[str, Any]:
        if not self.is_valid_url(url):
            raise HTTPException(status_code=400, detail="Invalid URL")

        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in info.get("formats", []):
            format_id = str(item.get("format_id") or "")
            resolution = item.get("resolution") or (str(item.get("height")) + "p" if item.get("height") else None)
            quality = item.get("format_note") or item.get("quality") or resolution
            ext = item.get("ext")
            entry = {
                "format_id": format_id,
                "ext": ext,
                "resolution": resolution,
                "quality": quality,
                "mime_type": item.get("vcodec") or item.get("acodec") or "video/mp4",
            }
            key = f"{format_id}:{ext}:{resolution}"
            if key in seen:
                continue
            seen.add(key)
            if entry["ext"] or entry["resolution"] or entry["quality"]:
                formats.append(entry)

        return {
            "url": url,
            "title": info.get("title"),
            "formats": formats[:20],
        }

    def create_job(self, db: Session, url: str, output_format: str, quality: str) -> DownloadJob:
        job = DownloadJob(
            id=str(uuid.uuid4()),
            url=url,
            status="queued",
            output_format=output_format,
            quality=quality,
            progress=0.0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    async def process_job(self, job_id: str) -> None:
        db = SessionLocal()
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).one_or_none()
        if not job:
            db.close()
            return

        try:
            job.status = "processing"
            job.progress = 0.15
            db.commit()

            output_base = self.storage_dir / f"{job.id}"
            ydl_opts: dict[str, Any] = {
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "outtmpl": str(output_base) + ".%(ext)s",
                "format": self._select_format(job.output_format, job.quality),
            }

            if job.output_format == "mp3":
                ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([job.url])

            created_files = sorted(self.storage_dir.glob(f"{job.id}*"))
            if not created_files:
                raise FileNotFoundError("No file was created for this job.")

            source_path = created_files[0]
            final_name = self.sanitize_name(self._extract_title_from_url(job.url))[:80] or "download"

            if job.output_format == "mp4":
                final_path = self.storage_dir / f"{final_name}-{job.id}.mp4"
                if source_path.suffix.lower() != ".mp4":
                    final_path = self._convert_video_to_mp4(source_path, final_path, job.quality)
                else:
                    final_path = source_path.rename(final_path)
            else:
                final_path = self.storage_dir / f"{final_name}-{job.id}.mp3"
                if source_path.suffix.lower() != ".mp3":
                    final_path = self._convert_to_mp3(source_path, final_path)
                else:
                    final_path = source_path.rename(final_path)

            file_record = DownloadedFile(
                id=str(uuid.uuid4()),
                job_id=job.id,
                file_name=final_path.name,
                storage_path=str(final_path),
                mime_type=mimetypes.guess_type(final_path.name)[0] or "application/octet-stream",
                size_bytes=final_path.stat().st_size,
            )
            db.add(file_record)

            job.status = "completed"
            job.download_url = f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/files/{file_record.id}"
            job.output_path = str(final_path)
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
        except Exception as exc:  # pragma: no cover - runtime-only handling
            job.status = "failed"
            job.error_message = str(exc)
            job.progress = 0.0
            job.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def _extract_title_from_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.path.strip("/").split("/")[-1] or "download"
        except Exception:
            return "download"

    def _select_format(self, output_format: str, quality: str) -> str:
        height = self.quality_to_height(quality)
        if output_format == "mp3":
            return "bestaudio/best"
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"

    def _convert_video_to_mp4(self, source: Path, target: Path, quality: str) -> Path:
        height = self.quality_to_height(quality)
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"scale=-2:{height}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(target),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return target

    def _convert_to_mp3(self, source: Path, target: Path) -> Path:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(target),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return target


downloader_service = DownloaderService()
