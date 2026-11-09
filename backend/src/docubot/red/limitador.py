"""Ritmo de peticiones por dominio.

Dentro de un proceso, todas las peticiones a un mismo host pasan por aquí:
- como máximo `simultaneas` a la vez;
- entre el inicio de una y el de la siguiente, al menos 1/peticiones_por_segundo
  (o el Crawl-delay del sitio, si es mayor);
- tras un 429/503, el host queda en pausa el tiempo indicado.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class _Host:
    semaforo: asyncio.Semaphore
    candado: asyncio.Lock = field(default_factory=asyncio.Lock)
    siguiente: float = 0.0  # momento (reloj del loop) a partir del cual se puede pedir
    intervalo_extra: float = 0.0  # Crawl-delay


class LimitadorPorDominio:
    def __init__(self, peticiones_por_segundo: float = 1.0, simultaneas: int = 2) -> None:
        if peticiones_por_segundo <= 0:
            raise ValueError("peticiones_por_segundo debe ser mayor que 0")
        self.intervalo = 1.0 / peticiones_por_segundo
        self.simultaneas = simultaneas
        self._hosts: dict[str, _Host] = {}

    def _host(self, host: str) -> _Host:
        estado = self._hosts.get(host)
        if estado is None:
            estado = self._hosts[host] = _Host(asyncio.Semaphore(self.simultaneas))
        return estado

    def fijar_retraso(self, host: str, segundos: float) -> None:
        """Crawl-delay del sitio (se usa si es mayor que el intervalo propio)."""
        self._host(host).intervalo_extra = max(0.0, segundos)

    def pausar(self, host: str, segundos: float) -> None:
        """Nadie pide a este host durante `segundos` (p. ej. tras un 429)."""
        estado = self._host(host)
        estado.siguiente = max(estado.siguiente, asyncio.get_running_loop().time() + segundos)

    @asynccontextmanager
    async def turno(self, host: str) -> AsyncIterator[None]:
        estado = self._host(host)
        reloj = asyncio.get_running_loop()
        async with estado.semaforo:
            async with estado.candado:
                espera = estado.siguiente - reloj.time()
                if espera > 0:
                    await asyncio.sleep(espera)
                estado.siguiente = reloj.time() + max(self.intervalo, estado.intervalo_extra)
            yield
