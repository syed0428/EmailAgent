"""
Phase 1 verification script.
Run this from the backend/ directory:

    python verify.py

It checks every subsystem independently before you start the server.
"""

import sys
import os
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make sure we can import app.*
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

OK   = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"


def check(label, fn):
    try:
        result = fn()
        print(f"  {OK}  {label}: {result}")
        return True
    except Exception as exc:
        print(f"  {FAIL}  {label}: {exc}")
        return False


print("\n==========================================")
print("  EmailAgent -- Phase 1 Verification")
print("==========================================\n")

passed = 0
total = 0

# ── 1. Config ─────────────────────────────────────────────────────────────────
total += 1
print("[1] Config")
if check("Settings loaded", lambda: __import__("app.core.config", fromlist=["get_settings"]).get_settings().llm_model):
    passed += 1

# ── 2. FastAPI importable ─────────────────────────────────────────────────────
total += 1
print("\n[2] FastAPI")
if check("App importable", lambda: str(__import__("app.main", fromlist=["app"]).app.title)):
    passed += 1

# ── 3. PostgreSQL ─────────────────────────────────────────────────────────────
total += 1
print("\n[3] PostgreSQL")
def pg_check():
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    s = get_settings()
    eng = create_engine(s.database_url, pool_pre_ping=True)
    with eng.connect() as c:
        row = c.execute(text("SELECT version()")).fetchone()
    return row[0][:40]
if check("Connection", pg_check):
    passed += 1

# ── 4. pgvector ───────────────────────────────────────────────────────────────
total += 1
print("\n[4] pgvector")
def pgvec_check():
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    s = get_settings()
    eng = create_engine(s.database_url)
    with eng.connect() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        c.commit()
        row = c.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).fetchone()
    return f"v{row[0]}"
if check("Extension available", pgvec_check):
    passed += 1

# ── 5. Ollama reachable ───────────────────────────────────────────────────────
total += 1
print("\n[5] Ollama")
def ollama_check():
    from app.services.ai_service import get_ai_service
    ai = get_ai_service()
    ok = ai.health_check()
    if not ok:
        raise RuntimeError("Ollama not reachable")
    return "reachable"
if check("Reachable", ollama_check):
    passed += 1

# ── 6. LLM test ───────────────────────────────────────────────────────────────
total += 1
print("\n[6] LLM generation")
def llm_check():
    from app.services.ai_service import get_ai_service
    ai = get_ai_service()
    resp = ai._chat("Say hello in 5 words.", timeout=60)
    return resp[:60]
if check("Generate response", llm_check):
    passed += 1

# ── 7. Embedding model ────────────────────────────────────────────────────────
total += 1
print("\n[7] Embedding model")
def emb_check():
    from app.services.embedding_service import get_embedding_service
    svc = get_embedding_service()
    vec = svc.embed("test sentence")
    return f"{svc.model_name} -> {len(vec)}d"
if check("Generate embedding", emb_check):
    passed += 1

# ── 8. pgvector insert + search ───────────────────────────────────────────────
total += 1
print("\n[8] Vector insert + similarity search")
def vec_search_check():
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    from app.services.embedding_service import get_embedding_service
    s = get_settings()
    eng = create_engine(s.database_url)
    svc = get_embedding_service()
    dims = s.embedding_dimensions
    v1 = svc.embed("machine learning engineer job")
    v2 = svc.embed("hiring software developer position")
    v_str1 = "[" + ",".join(str(x) for x in v1) + "]"
    v_str2 = "[" + ",".join(str(x) for x in v2) + "]"
    with eng.connect() as c:
        c.execute(text(f"CREATE TEMP TABLE _test_vecs (v vector({dims}))"))
        c.execute(text("INSERT INTO _test_vecs VALUES (:v ::vector)"), {"v": v_str1})
        c.execute(text("INSERT INTO _test_vecs VALUES (:v ::vector)"), {"v": v_str2})
        row = c.execute(
            text("SELECT 1 - (v <=> :q ::vector) AS sim FROM _test_vecs ORDER BY sim DESC LIMIT 1"),
            {"q": v_str1},
        ).fetchone()
        c.execute(text("DROP TABLE _test_vecs"))
        c.commit()
    return f"top similarity = {round(row[0], 4)}"
if check("Insert + cosine search", vec_search_check):
    passed += 1

# ── 9. DB table creation ──────────────────────────────────────────────────────
total += 1
print("\n[9] Database table creation")
def tables_check():
    from app.db.database import init_db
    init_db()
    return "all tables created"
if check("init_db()", tables_check):
    passed += 1

# -- Summary ------------------------------------------------------------------
print(f"\n==========================================")
print(f"  Result: {passed}/{total} checks passed")
print(f"==========================================\n")
if passed < total:
    sys.exit(1)
