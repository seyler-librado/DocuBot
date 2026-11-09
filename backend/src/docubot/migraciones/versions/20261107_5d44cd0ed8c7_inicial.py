"""Esquema inicial: perfiles, corridas, sitios, candidatos, documentos, fichas, lugares y cola.

Revision ID: 5d44cd0ed8c7
Revises:
Create Date: 2026-11-07 00:52:09.832889
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "5d44cd0ed8c7"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documentos",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("ruta", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime", sa.String(length=100), server_default="application/pdf", nullable=False),
        sa.Column("paginas", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=20), server_default="descargado", nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documentos")),
        sa.UniqueConstraint("sha256", name=op.f("uq_documentos_sha256")),
    )
    op.create_geospatial_table(
        "lugares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("catalogo", sa.String(length=50), nullable=False),
        sa.Column("clave", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=300), nullable=False),
        sa.Column("alias", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("nivel", sa.String(length=30), nullable=False),
        sa.Column("padre_id", sa.Integer(), nullable=True),
        sa.Column(
            "punto",
            Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "geom",
            Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "datos", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["padre_id"], ["lugares.id"], name=op.f("fk_lugares_padre_id_lugares"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lugares")),
        sa.UniqueConstraint("catalogo", "clave", name=op.f("uq_lugares_catalogo")),
    )
    op.create_geospatial_index(
        "ix_lugares_geom", "lugares", ["geom"], unique=False, postgresql_using="gist", postgresql_ops={}
    )
    op.create_index(op.f("ix_lugares_padre_id"), "lugares", ["padre_id"], unique=False)
    op.create_geospatial_index(
        "ix_lugares_punto", "lugares", ["punto"], unique=False, postgresql_using="gist", postgresql_ops={}
    )
    op.create_table(
        "perfiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("huella", sa.String(length=64), server_default="", nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_perfiles")),
        sa.UniqueConstraint("nombre", name=op.f("uq_perfiles_nombre")),
    )
    op.create_table(
        "corridas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("perfil_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=20), server_default="pendiente", nullable=False),
        sa.Column(
            "parametros", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "contadores", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creada", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("iniciada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminada", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["perfil_id"], ["perfiles.id"], name=op.f("fk_corridas_perfil_id_perfiles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_corridas")),
    )
    op.create_index(op.f("ix_corridas_perfil_id"), "corridas", ["perfil_id"], unique=False)
    op.create_table(
        "documento_lugares",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("documento_id", sa.BigInteger(), nullable=False),
        sa.Column("lugar_id", sa.Integer(), nullable=True),
        sa.Column("origen", sa.String(length=20), nullable=False),
        sa.Column("confianza", sa.Float(), server_default="0", nullable=False),
        sa.Column("estado", sa.String(length=20), server_default="asignado", nullable=False),
        sa.Column("candidatos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["documento_id"],
            ["documentos.id"],
            name=op.f("fk_documento_lugares_documento_id_documentos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lugar_id"], ["lugares.id"], name=op.f("fk_documento_lugares_lugar_id_lugares"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documento_lugares")),
        sa.UniqueConstraint("documento_id", "lugar_id", name=op.f("uq_documento_lugares_documento_id")),
    )
    op.create_index(op.f("ix_documento_lugares_documento_id"), "documento_lugares", ["documento_id"], unique=False)
    op.create_index(op.f("ix_documento_lugares_lugar_id"), "documento_lugares", ["lugar_id"], unique=False)
    op.create_table(
        "fichas",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("documento_id", sa.BigInteger(), nullable=False),
        sa.Column("perfil_id", sa.Integer(), nullable=False),
        sa.Column(
            "campos", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("estado", sa.String(length=20), server_default="revision", nullable=False),
        sa.Column("confianza", sa.String(length=10), nullable=True),
        sa.Column("motivos", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("modelo", sa.String(length=100), nullable=True),
        sa.Column("version_prompt", sa.String(length=50), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.id"], name=op.f("fk_fichas_documento_id_documentos"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["perfil_id"], ["perfiles.id"], name=op.f("fk_fichas_perfil_id_perfiles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fichas")),
        sa.UniqueConstraint("documento_id", "perfil_id", name=op.f("uq_fichas_documento_id")),
    )
    op.create_index(op.f("ix_fichas_perfil_id"), "fichas", ["perfil_id"], unique=False)
    op.create_table(
        "sitios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dominio", sa.String(length=255), nullable=False),
        sa.Column("estado", sa.String(length=20), server_default="nuevo", nullable=False),
        sa.Column("origen", sa.String(length=30), server_default="", nullable=False),
        sa.Column("lugar_id", sa.Integer(), nullable=True),
        sa.Column("robots_txt", sa.Text(), nullable=True),
        sa.Column("ultima_visita", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "datos", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lugar_id"], ["lugares.id"], name=op.f("fk_sitios_lugar_id_lugares"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sitios")),
        sa.UniqueConstraint("dominio", name=op.f("uq_sitios_dominio")),
    )
    op.create_index(op.f("ix_sitios_lugar_id"), "sitios", ["lugar_id"], unique=False)
    op.create_table(
        "textos",
        sa.Column("documento_id", sa.BigInteger(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("metodo", sa.String(length=20), nullable=False),
        sa.Column("caracteres", sa.Integer(), nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.id"], name=op.f("fk_textos_documento_id_documentos"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("documento_id", name=op.f("pk_textos")),
    )
    op.create_table(
        "candidatos",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("perfil_id", sa.Integer(), nullable=False),
        sa.Column("corrida_id", sa.Integer(), nullable=True),
        sa.Column("sitio_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("clave_url", sa.Text(), nullable=False),
        sa.Column("fuente", sa.String(length=30), nullable=False),
        sa.Column("ancla", sa.Text(), nullable=True),
        sa.Column("pagina_origen", sa.Text(), nullable=True),
        sa.Column("profundidad", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=50), nullable=True),
        sa.Column("puntaje", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=20), server_default="nuevo", nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("documento_id", sa.BigInteger(), nullable=True),
        sa.Column("lugar_id", sa.Integer(), nullable=True),
        sa.Column(
            "datos", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("creado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["corrida_id"], ["corridas.id"], name=op.f("fk_candidatos_corrida_id_corridas"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.id"], name=op.f("fk_candidatos_documento_id_documentos"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["lugar_id"], ["lugares.id"], name=op.f("fk_candidatos_lugar_id_lugares"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["perfil_id"], ["perfiles.id"], name=op.f("fk_candidatos_perfil_id_perfiles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["sitio_id"], ["sitios.id"], name=op.f("fk_candidatos_sitio_id_sitios"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidatos")),
        sa.UniqueConstraint("perfil_id", "clave_url", name=op.f("uq_candidatos_perfil_id")),
    )
    op.create_index(op.f("ix_candidatos_corrida_id"), "candidatos", ["corrida_id"], unique=False)
    op.create_index(op.f("ix_candidatos_documento_id"), "candidatos", ["documento_id"], unique=False)
    op.create_index(op.f("ix_candidatos_estado"), "candidatos", ["estado"], unique=False)
    op.create_index(op.f("ix_candidatos_lugar_id"), "candidatos", ["lugar_id"], unique=False)
    op.create_index(op.f("ix_candidatos_sitio_id"), "candidatos", ["sitio_id"], unique=False)
    op.create_table(
        "tareas",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("etapa", sa.String(length=30), nullable=False),
        sa.Column("corrida_id", sa.Integer(), nullable=True),
        sa.Column(
            "carga", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("estado", sa.String(length=20), server_default="pendiente", nullable=False),
        sa.Column("prioridad", sa.Integer(), server_default="0", nullable=False),
        sa.Column("intentos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_intentos", sa.Integer(), server_default="3", nullable=False),
        sa.Column("disponible_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tomada_por", sa.String(length=100), nullable=True),
        sa.Column("tomada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creada", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("terminada", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["corrida_id"], ["corridas.id"], name=op.f("fk_tareas_corrida_id_corridas"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tareas")),
    )
    op.create_index(op.f("ix_tareas_corrida_id"), "tareas", ["corrida_id"], unique=False)
    op.create_index(
        "ix_tareas_pendientes",
        "tareas",
        ["etapa", "prioridad", "id"],
        unique=False,
        postgresql_where=sa.text("estado = 'pendiente'"),
    )


def downgrade() -> None:
    op.drop_index("ix_tareas_pendientes", table_name="tareas", postgresql_where=sa.text("estado = 'pendiente'"))
    op.drop_index(op.f("ix_tareas_corrida_id"), table_name="tareas")
    op.drop_table("tareas")
    op.drop_index(op.f("ix_candidatos_sitio_id"), table_name="candidatos")
    op.drop_index(op.f("ix_candidatos_lugar_id"), table_name="candidatos")
    op.drop_index(op.f("ix_candidatos_estado"), table_name="candidatos")
    op.drop_index(op.f("ix_candidatos_documento_id"), table_name="candidatos")
    op.drop_index(op.f("ix_candidatos_corrida_id"), table_name="candidatos")
    op.drop_table("candidatos")
    op.drop_table("textos")
    op.drop_index(op.f("ix_sitios_lugar_id"), table_name="sitios")
    op.drop_table("sitios")
    op.drop_index(op.f("ix_fichas_perfil_id"), table_name="fichas")
    op.drop_table("fichas")
    op.drop_index(op.f("ix_documento_lugares_lugar_id"), table_name="documento_lugares")
    op.drop_index(op.f("ix_documento_lugares_documento_id"), table_name="documento_lugares")
    op.drop_table("documento_lugares")
    op.drop_index(op.f("ix_corridas_perfil_id"), table_name="corridas")
    op.drop_table("corridas")
    op.drop_table("perfiles")
    op.drop_geospatial_index("ix_lugares_punto", table_name="lugares", postgresql_using="gist", column_name="punto")
    op.drop_index(op.f("ix_lugares_padre_id"), table_name="lugares")
    op.drop_geospatial_index("ix_lugares_geom", table_name="lugares", postgresql_using="gist", column_name="geom")
    op.drop_geospatial_table("lugares")
    op.drop_table("documentos")
