"""Retrieve relevant context from pgvector (Postgres)."""

import sqlalchemy
from sentence_transformers import SentenceTransformer

from app.config import settings

_MODEL: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _MODEL


class RAGRetriever:
    def __init__(self):
        self.model = _get_model()

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """Search for relevant chunks in rpml_chunks (pgvector)."""
        engine = sqlalchemy.create_engine(settings.database_url_sync)
        embedding = self.model.encode(query).tolist()
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    sqlalchemy.text(
                        "SELECT content FROM rpml_chunks ORDER BY embedding <=> :vec::vector LIMIT :k"
                    ),
                    {"vec": vec_str, "k": top_k},
                )
                return [r[0] for r in rows]
        finally:
            engine.dispose()
