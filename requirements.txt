from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.downloads import router as downloads_router
from app.api.routers.health import router as health_router
from app.core.config import settings
from app.db.database import Base, engine


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="REST API for downloading and converting media from supported video platforms.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(downloads_router)

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)

    return app


app = create_app()
