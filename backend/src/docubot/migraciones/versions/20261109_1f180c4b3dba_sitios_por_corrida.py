"""Sitios por corrida: cada corrida explora un sitio una sola vez.

Revision ID: 1f180c4b3dba
Revises: 5d44cd0ed8c7
Create Date: 2026-11-09 17:35:10.162162
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1f180c4b3dba"
down_revision: str | None = "5d44cd0ed8c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corrida_sitios",
        sa.Column("corrida_id", sa.Integer(), nullable=False),
        sa.Column("sitio_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=20), server_default="pendiente", nullable=False),
        sa.Column("origen", sa.String(length=30), server_default="", nullable=False),
        sa.Column(
            "semillas", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("lugar", sa.String(length=50), nullable=True),
        sa.Column("paginas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("documentos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("segundos", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("terminado", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["corrida_id"], ["corridas.id"], name=op.f("fk_corrida_sitios_corrida_id_corridas"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["sitio_id"], ["sitios.id"], name=op.f("fk_corrida_sitios_sitio_id_sitios"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("corrida_id", "sitio_id", name=op.f("pk_corrida_sitios")),
    )
    op.create_index(op.f("ix_corrida_sitios_sitio_id"), "corrida_sitios", ["sitio_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_corrida_sitios_sitio_id"), table_name="corrida_sitios")
    op.drop_table("corrida_sitios")
