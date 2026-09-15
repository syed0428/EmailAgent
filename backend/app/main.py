"""
FastAPI Application Entry Point
"""

import sys
import os

# Patch tqdm BEFORE any other imports — redirect all progress bars to stderr
# This prevents Windows [Errno 22] when tqdm tries to write to uvicorn's
# captured stdout inside a thread pool executor
try:
    import tqdm
    import tqdm.auto
    # Monkey-patch tqdm to always write to stderr
    _original_tqdm_init = tqdm.tqdm.__init__
    def _patched_tqdm_init(self, *args, **kwargs):
        kwargs.setdefault("file", sys.stderr)
        kwargs["disable"] = True          # disable all tqdm bars in server context
        _original_tqdm_init(self, *args, **kwargs)
    tqdm.tqdm.__init__ = _patched_tqdm_init
    tqdm.auto.tqdm.__init__ = _patched_tqdm_init
except Exception:
    pass

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.database import init_db
from app.api.routes import health, emails, jobs, auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database…")
    try:
        init_db()
        logger.info("Database initialised OK")
    except Exception as exc:
        logger.error(f"Database init failed: {exc}")

    # Warm up embedding model in the main thread (avoids Windows Errno 22
    # that occurs when SentenceTransformer first loads inside a thread pool)
    logger.info("Warming up embedding model…")
    try:
        from app.services.embedding_service import get_embedding_service
        svc = get_embedding_service()
        svc.embed("warmup")
        logger.info(f"Embedding model ready: {svc.model_name}")
    except Exception as exc:
        logger.warning(f"Embedding warmup failed (non-fatal): {exc}")

    yield
    logger.info("Shutting down")


app = FastAPI(
    title="EmailAgent API",
    description=(
        "AI-powered email management backend. "
        "Gmail OAuth · pgvector semantic search · Ollama LLM"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS (allow Vite dev server) ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api")
app.include_router(emails.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(auth.router, prefix="/api")

# Alias for legacy or alternative redirect URIs (e.g. /api/gmail/oauth/callback)
app.add_api_route(
    "/api/gmail/oauth/callback",
    auth.google_callback,
    methods=["GET"],
    include_in_schema=False,
)


@app.get("/")
def root():
    return {
        "service": "EmailAgent API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health/full",
    }
