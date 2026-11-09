"""Motor y sesiones de la base de datos (SQLAlchemy async con psycopg 3)."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from docubot.ajustes import obtener_ajustes


@lru_cache
def obtener_motor() -> AsyncEngine:
    return create_async_engine(obtener_ajustes().base_datos_url, pool_pre_ping=True)


@lru_cache
def fabrica_sesiones() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(obtener_motor(), expire_on_commit=False)


async def sesion_api() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI: una sesión por petición."""
    async with fabrica_sesiones()() as sesion:
        yield sesion
