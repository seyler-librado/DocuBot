"""Las pruebas usan su propia base (docubot_pruebas), nunca la de trabajo.

Se corren con: docker compose --profile pruebas run --rm pruebas
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parent))  # para importar tests/simulado.py

URL_TRABAJO = os.environ.get("DOCUBOT_BASE_DATOS_URL", "postgresql+psycopg://docubot:docubot@localhost:5433/docubot")
_partes = urlsplit(URL_TRABAJO)
URL_PRUEBAS = urlunsplit(_partes._replace(path="/docubot_pruebas"))
# antes de importar docubot: todo lo que lea los ajustes apunta a la base de pruebas
os.environ["DOCUBOT_BASE_DATOS_URL"] = URL_PRUEBAS
os.environ.setdefault("DOCUBOT_CONFIG", "/no-existe.yaml")
# las pruebas nunca hablan con una IA real (aunque .env configure una)
for _variable in [k for k in os.environ if k.startswith("DOCUBOT_IA__")]:
    del os.environ[_variable]
os.environ["DOCUBOT_IA__PROVEEDOR"] = "ninguno"
os.environ["DOCUBOT_BUSQUEDA__EMBEDDINGS"] = "ninguno"  # ni descargar modelos: cada prueba usa uno simulado

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from docubot.ajustes import obtener_ajustes  # noqa: E402
from docubot.db.sesion import obtener_motor  # noqa: E402


def _conexion_admin() -> psycopg.Connection:
    dsn = urlunsplit(_partes._replace(scheme="postgresql", path="/postgres"))
    return psycopg.connect(dsn, autocommit=True)


@pytest.fixture(scope="session", autouse=True)
def base_de_pruebas():
    """Crea la base de pruebas desde cero y le aplica las migraciones."""
    try:
        admin = _conexion_admin()
    except psycopg.OperationalError as error:
        pytest.skip(f"sin Postgres para pruebas: {error}")
    with admin:
        admin.execute("DROP DATABASE IF EXISTS docubot_pruebas WITH (FORCE)")
        admin.execute("CREATE DATABASE docubot_pruebas")

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", "docubot:migraciones")
    cfg.set_main_option("sqlalchemy.url", URL_PRUEBAS)
    command.upgrade(cfg, "head")
    obtener_ajustes.cache_clear()
    yield


@pytest.fixture
async def sesiones():
    motor = create_async_engine(URL_PRUEBAS, poolclass=NullPool)
    async with motor.begin() as c:
        await c.execute(
            text("TRUNCATE tareas, corridas, perfiles, sitios, documentos, lugares, catalogos RESTART IDENTITY CASCADE")
        )
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


@pytest.fixture(autouse=True)
async def _cerrar_motor_global():
    """El motor global guarda conexiones del loop de cada prueba; se cierra al final."""
    yield
    await obtener_motor().dispose()
