"""Entorno de Alembic. La URL sale de los ajustes de DocuBot (DOCUBOT_BASE_DATOS_URL)."""

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine, pool

from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Base

config = context.config
metadatos = Base.metadata

# Tablas y esquemas que crea PostGIS por su cuenta; Alembic no debe tocarlos.
AJENAS = {"spatial_ref_sys", "layer", "topology"}


def incluir_nombre(nombre, tipo, padres) -> bool:
    if tipo == "schema":
        return nombre in (None, "public")
    if tipo == "table":
        return nombre not in AJENAS
    return True


def url() -> str:
    return config.get_main_option("sqlalchemy.url") or obtener_ajustes().base_datos_url


def correr_sin_conexion() -> None:
    context.configure(
        url=url(),
        target_metadata=metadatos,
        literal_binds=True,
        include_name=incluir_nombre,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def correr_con_conexion() -> None:
    motor = create_engine(url(), poolclass=pool.NullPool)
    with motor.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=metadatos,
            include_name=incluir_nombre,
            include_schemas=False,
            render_item=alembic_helpers.render_item,
            process_revision_directives=alembic_helpers.writer,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    correr_sin_conexion()
else:
    correr_con_conexion()
