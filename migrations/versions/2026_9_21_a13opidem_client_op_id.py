"""client_op_id en consultas

Revision ID: a13opidem
Revises: a12consultadoc
Create Date: 2026-09-21 10:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "a13opidem"
down_revision = "a12consultadoc"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("consultas", sa.Column("client_op_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_consultas_usuario_client_op", "consultas", ["usuario_id", "client_op_id"])

def downgrade():
    op.drop_constraint("uq_consultas_usuario_client_op", "consultas", type_="unique")
    op.drop_column("consultas", "client_op_id")
