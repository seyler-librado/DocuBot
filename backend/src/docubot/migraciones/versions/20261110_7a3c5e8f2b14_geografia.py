"""Geografía: catálogos importados, catálogo de cada ubicación y unaccent para buscar lugares.

Revision ID: 7a3c5e8f2b14
Revises: 4d7e2b9c1a05
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a3c5e8f2b14"
down_revision: str | None = "4d7e2b9c1a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_table(
        "catalogos",
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("lugares", sa.Integer(), server_default="0", nullable=False),
        sa.Column("actualizado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("nombre", name=op.f("pk_catalogos")),
    )
    op.add_column("documento_lugares", sa.Column("catalogo", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_documento_lugares_catalogo"), "documento_lugares", ["catalogo"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_documento_lugares_catalogo"), table_name="documento_lugares")
    op.drop_column("documento_lugares", "catalogo")
    op.drop_table("catalogos")
