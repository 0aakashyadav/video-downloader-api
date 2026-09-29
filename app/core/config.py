from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Video Downloader API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/video_downloader"
    SECRET_KEY: str = "change-me-in-production"
    UPLOAD_DIR: str = "/tmp/video_downloader"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    MAX_CONCURRENT_JOBS: int = 3
    ALLOWED_OUTPUT_FORMATS: list[str] = ["mp4", "mp3"]
    ALLOWED_QUALITIES: list[str] = ["360p", "480p", "720p", "1080p"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
