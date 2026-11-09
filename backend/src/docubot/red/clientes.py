"""Clientes HTTP compartidos dentro de un proceso.

El ritmo por dominio vive en cada Cliente: si cada tarea creara el suyo, dos
tareas que piden al mismo sitio no se coordinarían. Por eso se comparten:

- `web(...)`: para sitios, con robots.txt y ritmo (un cliente por combinación
  de ajustes de perfil);
- `api()`: para APIs de buscadores e índices (sin robots.txt, timeout largo).
"""

import logging

import httpx

from docubot.ajustes import obtener_ajustes
from docubot.red.cliente import Cliente

log = logging.getLogger("docubot.red")
_clientes: dict[tuple, Cliente] = {}
_transporte: httpx.AsyncBaseTransport | None = None  # solo para pruebas
_espera_base: float = 2.0
_ritmo_api: float = 1.0


def usar_transporte(
    transporte: httpx.AsyncBaseTransport | None, espera_base: float = 2.0, ritmo_api: float = 1.0
) -> None:
    """Pruebas: todos los clientes nuevos usan este transporte simulado."""
    global _transporte, _espera_base, _ritmo_api
    _transporte, _espera_base, _ritmo_api = transporte, espera_base, ritmo_api
    _clientes.clear()


def web(peticiones_por_segundo: float | None = None, respetar_robots: bool | None = None) -> Cliente:
    clave = ("web", peticiones_por_segundo, respetar_robots)
    if clave not in _clientes:
        if respetar_robots is False or (respetar_robots is None and not obtener_ajustes().red.respetar_robots):
            log.warning("robots.txt desactivado: se pedirán también las rutas que los sitios excluyen")
        _clientes[clave] = Cliente(
            peticiones_por_segundo=peticiones_por_segundo,
            respetar_robots=respetar_robots,
            transporte=_transporte,
            espera_base=_espera_base,
        )
    return _clientes[clave]


def api() -> Cliente:
    if ("api",) not in _clientes:
        red = obtener_ajustes().red
        ajustes = red.model_copy(update={"timeout": max(red.timeout, 90.0), "max_mb_pagina": 50})
        _clientes[("api",)] = Cliente(
            ajustes,
            respetar_robots=False,
            peticiones_por_segundo=_ritmo_api,
            transporte=_transporte,
            espera_base=_espera_base,
        )
    return _clientes[("api",)]


async def cerrar_todos() -> None:
    for cliente in list(_clientes.values()):
        await cliente.cerrar()
    _clientes.clear()
