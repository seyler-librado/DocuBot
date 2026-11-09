"""Búsqueda: texto completo en español sin acentos y fragmentos con vectores.

Revision ID: 9e1f3a7c5d22
Revises: 7a3c5e8f2b14
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9e1f3a7c5d22"
down_revision: str | None = "7a3c5e8f2b14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSV_TEXTO = "to_tsvector('docubot_es'::regconfig, left(contenido, 400000))"
TSV_FICHA = (
    "setweight(to_tsvector('docubot_es'::regconfig, coalesce(campos ->> 'titulo', campos ->> 'nombre', '')), 'A') || "
    "setweight(jsonb_to_tsvector('docubot_es'::regconfig, campos, '[\"string\"]'), 'B')"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # español, sin acentos: «planeacion» encuentra «Planeación», «reglamentos» encuentra «reglamento»
    op.execute("CREATE TEXT SEARCH CONFIGURATION docubot_es (COPY = pg_catalog.spanish)")
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION docubot_es ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem"
    )
    op.add_column(
        "textos", sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(TSV_TEXTO, persisted=True), nullable=True)
    )
    op.create_index("ix_textos_tsv", "textos", ["tsv"], postgresql_using="gin")
    op.add_column(
        "fichas", sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(TSV_FICHA, persisted=True), nullable=True)
    )
    op.create_index("ix_fichas_tsv", "fichas", ["tsv"], postgresql_using="gin")
    op.create_table(
        "fragmentos",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("documento_id", sa.BigInteger(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("modelo", sa.String(length=200), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(), nullable=False),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.id"], name=op.f("fk_fragmentos_documento_id_documentos"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fragmentos")),
    )
    op.create_index(op.f("ix_fragmentos_documento_id"), "fragmentos", ["documento_id"], unique=False)
    op.create_index(op.f("ix_fragmentos_modelo"), "fragmentos", ["modelo"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fragmentos_modelo"), table_name="fragmentos")
    op.drop_index(op.f("ix_fragmentos_documento_id"), table_name="fragmentos")
    op.drop_table("fragmentos")
    op.drop_index("ix_fichas_tsv", table_name="fichas")
    op.drop_column("fichas", "tsv")
    op.drop_index("ix_textos_tsv", table_name="textos")
    op.drop_column("textos", "tsv")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS docubot_es")
