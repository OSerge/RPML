"""Index knowledge base documents into pgvector (Postgres)."""

from pathlib import Path

import sqlalchemy
from sentence_transformers import SentenceTransformer

from app.config import settings


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def index_knowledge_base(
    knowledge_dir: Path | None = None,
) -> int:
    """Index markdown documents into rpml_chunks (pgvector)."""
    knowledge_dir = knowledge_dir or Path(__file__).parent / "knowledge_base"
    model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    engine = sqlalchemy.create_engine(settings.database_url_sync)

    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("DELETE FROM rpml_chunks"))
        conn.commit()

    count = 0
    for md_file in knowledge_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        chunks = _chunk_text(text)
        for chunk in chunks:
            embedding = model.encode(chunk).tolist()
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            with engine.connect() as conn:
                conn.execute(
                    sqlalchemy.text(
                        "INSERT INTO rpml_chunks (content, source, embedding) VALUES (:content, :source, :vec::vector)"
                    ),
                    {"content": chunk, "source": md_file.name, "vec": vec_str},
                )
                conn.commit()
            count += 1
    engine.dispose()
    return count
