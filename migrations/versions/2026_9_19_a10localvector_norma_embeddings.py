"""Embeddings derivados; dimensión 1024 medida con qwen3-embedding:0.6b.

Migración revisada manualmente. No modifica normas, full-text ni historial.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "a10localvector"
down_revision = "9a03e8aa9ccb"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("norma_embeddings",
        sa.Column("norma_id", sa.Uuid(), sa.ForeignKey("normas.id"), primary_key=True),
        sa.Column("modelo", sa.String(), nullable=False),
        sa.Column("modelo_digest", sa.String(), nullable=False),
        sa.Column("contenido_hash", sa.String(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("vector", Vector(1024), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    # 1570 filas: búsqueda exacta evita pérdida de recall de un índice aproximado.


def downgrade():
    op.drop_table("norma_embeddings")
    # No eliminar la extensión: puede estar siendo utilizada por otras tablas.
