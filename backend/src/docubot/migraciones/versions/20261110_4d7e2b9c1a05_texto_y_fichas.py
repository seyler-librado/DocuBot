"""Texto y fichas: error de extracción, control de la ficha e índice de tareas únicas.

Revision ID: 4d7e2b9c1a05
Revises: 8c2f4e1a9b3d
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4d7e2b9c1a05"
down_revision: str | None = "8c2f4e1a9b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("textos", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "fichas",
        sa.Column(
            "control", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.execute("CREATE INDEX ix_tareas_clave ON tareas ((carga ->> 'clave')) WHERE estado IN ('pendiente', 'tomada')")


def downgrade() -> None:
    op.drop_index("ix_tareas_clave", table_name="tareas")
    op.drop_column("fichas", "control")
    op.drop_column("textos", "error")
