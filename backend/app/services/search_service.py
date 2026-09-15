"""
Semantic Search Service
───────────────────────
Uses pgvector cosine similarity to find emails related to a query.
"""

import logging
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.embedding_service import get_embedding_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SearchService:
    def __init__(self, db: Session):
        self.db = db
        self.embedder = get_embedding_service()

    def semantic_search(
        self,
        query: str,
        account_id: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> List[dict]:
        """Find emails semantically similar to query."""
        query_vector = self.embedder.embed(query)
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        sql = text("""
            SELECT
                e.id              AS email_id,
                e.gmail_id,
                e.subject,
                e.sender,
                e.snippet,
                e.received_at,
                ea.category,
                ea.importance,
                ea.summary,
                1 - (ee.embedding <=> :vector ::vector) AS similarity
            FROM email_embeddings ee
            JOIN emails e ON e.id = ee.email_id
            LEFT JOIN email_analysis ea ON ea.email_id = e.id
            WHERE (:account_id IS NULL OR e.account_id = :account_id ::uuid)
              AND 1 - (ee.embedding <=> :vector ::vector) >= :min_sim
            ORDER BY similarity DESC
            LIMIT :lim
        """)

        rows = self.db.execute(sql, {
            "vector": vector_str,
            "account_id": account_id,
            "min_sim": min_similarity,
            "lim": limit,
        }).mappings().all()

        return [dict(r) for r in rows]
