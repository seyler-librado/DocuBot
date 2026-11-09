"""Índice para encontrar rápido la tarea de descarga de un candidato.

Revision ID: 8c2f4e1a9b3d
Revises: 1f180c4b3dba
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8c2f4e1a9b3d"
down_revision: str | None = "1f180c4b3dba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_tareas_candidato ON tareas ((carga ->> 'candidato_id')) WHERE etapa = 'descargar'")


def downgrade() -> None:
    op.drop_index("ix_tareas_candidato", table_name="tareas")
