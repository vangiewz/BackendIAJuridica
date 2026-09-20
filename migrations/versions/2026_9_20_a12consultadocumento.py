"""Relaciona una consulta con el documento sobre el que se hizo.

Es una columna nullable: las consultas generales, que son la mayoria y todas las ya
guardadas, siguen sin documento. No se duplica nada del documento, solo se lo referencia.
"""
from alembic import op
import sqlalchemy as sa

revision = "a12consultadoc"
down_revision = "a11iaprogreso"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("consultas", sa.Column("documento_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_consultas_documento", "consultas", "documentos",
                          ["documento_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_consultas_documento_id", "consultas", ["documento_id"])


def downgrade():
    op.drop_index("ix_consultas_documento_id", table_name="consultas")
    op.drop_constraint("fk_consultas_documento", "consultas", type_="foreignkey")
    op.drop_column("consultas", "documento_id")
