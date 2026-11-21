from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ensure_data_dirs, settings
from app.db import Base, SessionLocal, engine
import app.models  # noqa: F401
from app.ai.gateway import gateway
from app.routers import briefs, demand_map, health, mapping, projects, research, settings_ai, topic_source


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_data_dirs()
    Base.metadata.create_all(bind=engine, checkfirst=True)
    db = SessionLocal()
    try:
        gateway.ensure_default_rows(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="FinZ SEO Workbench V1.6 — Human-in-the-loop Evidence-Based SEO Decision System",
    lifespan=lifespan,
)

# Restrict CORS strictly to local workbench origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    expose_headers=["X-FinZ-Export-Filename", "Content-Disposition"],
)

API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(settings_ai.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(topic_source.router, prefix=API_PREFIX)
app.include_router(demand_map.router, prefix=API_PREFIX)
app.include_router(research.router, prefix=API_PREFIX)
app.include_router(mapping.router, prefix=API_PREFIX)
app.include_router(briefs.router, prefix=API_PREFIX)
