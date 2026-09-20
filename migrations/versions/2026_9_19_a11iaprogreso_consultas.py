"""Estado de progreso IA; conserva consultas y respuestas existentes."""
from alembic import op
import sqlalchemy as sa

revision = "a11iaprogreso"
down_revision = "a10localvector"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("consultas", sa.Column("etapa_ia", sa.String(), nullable=True))
    op.add_column("consultas", sa.Column("ia_error", sa.String(), nullable=True))


def downgrade():
    op.drop_column("consultas", "ia_error")
    op.drop_column("consultas", "etapa_ia")
