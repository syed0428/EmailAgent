"""
Health-check endpoints — Phase 1 verification target.
Tests: FastAPI ✓, PostgreSQL ✓, pgvector ✓, Ollama ✓, Embeddings ✓
"""

import time
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import get_db
from app.services.ai_service import get_ai_service
from app.services.embedding_service import get_embedding_service
from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["Health"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/")
def health_root():
    return {"status": "ok", "service": "EmailAgent API"}


@router.get("/full")
def health_full(db: Session = Depends(get_db)):
    """
    Full stack health check.
    Returns the status of every subsystem needed for Phase 1 sign-off.
    """
    results = {}

    # ── 1. PostgreSQL ────────────────────────────────────────────────────────
    try:
        db.execute(text("SELECT 1"))
        results["postgres"] = {"status": "ok"}
    except Exception as exc:
        results["postgres"] = {"status": "error", "detail": str(exc)}

    # ── 2. pgvector extension ────────────────────────────────────────────────
    try:
        row = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()
        if row:
            results["pgvector"] = {"status": "ok", "version": row[0]}
        else:
            results["pgvector"] = {"status": "error", "detail": "extension not installed"}
    except Exception as exc:
        results["pgvector"] = {"status": "error", "detail": str(exc)}

    # ── 3. Ollama / LLM ──────────────────────────────────────────────────────
    try:
        ai = get_ai_service()
        ok = ai.health_check()
        results["ollama"] = {
            "status": "ok" if ok else "error",
            "model": settings.llm_model,
            "base_url": settings.ollama_base_url,
        }
    except Exception as exc:
        results["ollama"] = {"status": "error", "detail": str(exc)}

    # ── 4. Embedding model ────────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()
        embedder = get_embedding_service()
        # Use the already-warmed cached model; force no tqdm output
        vec = embedder.embed("health check")
        elapsed = round(time.perf_counter() - t0, 3)
        results["embeddings"] = {
            "status": "ok",
            "backend": settings.embedding_backend,
            "model": embedder.model_name,
            "dimensions": len(vec),
            "elapsed_s": elapsed,
        }
    except Exception as exc:
        results["embeddings"] = {"status": "error", "detail": str(exc)}

    # ── 5. pgvector write + similarity search ────────────────────────────────
    try:
        if results.get("pgvector", {}).get("status") == "ok" and \
           results.get("embeddings", {}).get("status") == "ok":
            embedder = get_embedding_service()
            dims = settings.embedding_dimensions
            test_vec = embedder.embed("semantic similarity test")
            vec_str = "[" + ",".join(str(v) for v in test_vec) + "]"
            # Insert into a temp table just to verify pgvector ops
            db.execute(text(f"CREATE TEMP TABLE IF NOT EXISTS _hc_vec (v vector({dims}))"))
            db.execute(text(f"INSERT INTO _hc_vec VALUES (:v ::vector)"), {"v": vec_str})
            row = db.execute(
                text(f"SELECT 1 - (v <=> :v ::vector) AS sim FROM _hc_vec LIMIT 1"),
                {"v": vec_str},
            ).fetchone()
            db.execute(text("DROP TABLE IF EXISTS _hc_vec"))
            db.commit()
            results["vector_search"] = {
                "status": "ok",
                "self_similarity": round(row[0], 6) if row else None,
            }
        else:
            results["vector_search"] = {"status": "skipped", "reason": "dependency failed"}
    except Exception as exc:
        results["vector_search"] = {"status": "error", "detail": str(exc)}

    overall = "ok" if all(v.get("status") == "ok" for v in results.values()) else "degraded"
    return {"overall": overall, "checks": results}
