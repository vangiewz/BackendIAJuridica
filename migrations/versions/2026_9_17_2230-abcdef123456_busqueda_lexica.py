"""busqueda lexica

Revision ID: abcdef123456
Revises: 48e30a8c7cc4
Create Date: 2026-09-17 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abcdef123456'
down_revision: Union[str, None] = '48e30a8c7cc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS es_unaccent;")
    op.execute("CREATE TEXT SEARCH CONFIGURATION es_unaccent (COPY = spanish);")
    op.execute("ALTER TEXT SEARCH CONFIGURATION es_unaccent ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem;")

    op.execute("""
        ALTER TABLE normas ADD COLUMN busqueda tsvector
        GENERATED ALWAYS AS (
            to_tsvector('es_unaccent'::regconfig, coalesce(epigrafe,'') || ' ' || texto)
        ) STORED;
    """)

    op.execute("CREATE INDEX ix_normas_busqueda ON normas USING GIN (busqueda);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_normas_busqueda;")
    op.execute("ALTER TABLE normas DROP COLUMN IF EXISTS busqueda;")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS es_unaccent;")
    op.execute("DROP EXTENSION IF EXISTS unaccent;")
