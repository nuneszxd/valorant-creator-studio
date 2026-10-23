"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import analysis as analysis_api
from .api import candidates as candidates_api
from .api import clips as clips_api
from .api import ideas as ideas_api
from .api import imports as imports_api
from .api import jobs as jobs_api
from .api import library as library_api
from .api import publications as publications_api
from .api import radar as radar_api
from .api import recordings as recordings_api
from .api import settings as settings_api
from .api import system as system_api
from .config import AppConfig
from .context import build_context
from .errors import AppError, NotFound
from .security import LocalOnlyMiddleware

log = logging.getLogger(__name__)

API_DESCRIPTION = (
    "API local do Valorant Creator Studio. Só responde em localhost; vídeos e áudios nunca saem "
    "da máquina. O contrato OpenAPI fica em /api/openapi.json (interface interativa em /api/docs "
    "com VCS_API_DOCS=1)."
)


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.is_file():

        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse(
                {
                    "app": "Valorant Creator Studio",
                    "message": "Interface ainda não compilada. Rode .\\setup.bat na pasta do projeto (ou 'npm run build' em frontend/).",
                    "api_docs": "/api/docs",
                }
            )

        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    dist_resolved = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise NotFound("Rota não encontrada.")
        # Never join drive-qualified, rooted or backslash paths: on Windows that can point at a network share.
        if full_path and not (full_path.startswith("/") or "\\" in full_path or ":" in full_path):
            candidate = (dist / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(dist_resolved):
                return FileResponse(candidate)
        return FileResponse(index)


def create_app(config: AppConfig | None = None) -> FastAPI:
    config = config or AppConfig.from_env()
    ctx = build_context(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        ctx.jobs.start()
        try:
            yield
        finally:
            ctx.jobs.stop()

    app = FastAPI(
        title="Valorant Creator Studio API",
        version=__version__,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs" if config.api_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.ctx = ctx

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(config.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type"],
    )
    # Added last => outermost: the Host/Origin guard runs before anything else.
    app.add_middleware(
        LocalOnlyMiddleware,
        allowed_hosts=config.allowed_hosts,
        allowed_origins=config.allowed_origins,
    )

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Erro interno. Consulte data/logs/app.log para detalhes.",
                    "details": None,
                }
            },
        )

    for module in ROUTER_MODULES:
        app.include_router(module.router)

    _mount_frontend(app, config.frontend_dist)
    return app


ROUTER_MODULES = [
    system_api,
    settings_api,
    jobs_api,
    recordings_api,
    imports_api,
    analysis_api,
    candidates_api,
    clips_api,
    publications_api,
    ideas_api,
    radar_api,
    library_api,
]
