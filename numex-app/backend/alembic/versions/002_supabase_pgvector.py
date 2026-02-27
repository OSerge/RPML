"""supabase pgvector and users.password_hash nullable

Revision ID: 002
Revises: 001
Create Date: 2025-02-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(255),
        nullable=True,
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS rpml_chunks (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            source VARCHAR(255),
            embedding vector(384)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS rpml_chunks_embedding_idx
        ON rpml_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rpml_chunks")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(255),
        nullable=False,
    )
