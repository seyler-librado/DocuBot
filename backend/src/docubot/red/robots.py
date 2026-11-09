"""Reglas de robots.txt por origen, con caché.

Criterio (el mismo que usan los buscadores grandes):
- 200: se aplican las reglas.
- 4xx (salvo 429): no hay reglas, se permite todo.
- 5xx o 429: se asume que no se permite nada, por un rato.
- sin conexión: se permite (si el sitio no responde, tampoco se le podrá pedir nada más).
"""

import time
from dataclasses import dataclass

from protego import Protego

VIGENCIA = 6 * 3600  # segundos que se guarda un robots.txt leído
VIGENCIA_FALLA = 10 * 60  # segundos que se guarda una respuesta 5xx o sin conexión
MAX_RETRASO = 60.0  # tope al Crawl-delay


@dataclass
class Reglas:
    """Lo que dice el robots.txt de un origen."""

    estado: str  # reglas | permitir_todo | negar_todo
    parser: Protego | None = None
    expira: float = 0.0
    detalle: str = ""

    def permite(self, url: str, agente: str) -> bool:
        if self.estado == "permitir_todo":
            return True
        if self.estado == "negar_todo" or self.parser is None:
            return False
        return self.parser.can_fetch(url, agente)

    def retraso(self, agente: str) -> float | None:
        if self.parser is None:
            return None
        valor = self.parser.crawl_delay(agente)
        return min(float(valor), MAX_RETRASO) if valor else None

    @property
    def vencida(self) -> bool:
        return time.monotonic() >= self.expira


def desde_respuesta(estado_http: int | None, texto: str = "", detalle: str = "") -> Reglas:
    ahora = time.monotonic()
    if estado_http is None:
        return Reglas("permitir_todo", expira=ahora + VIGENCIA_FALLA, detalle=detalle or "sin conexión")
    if 200 <= estado_http < 300:
        return Reglas("reglas", Protego.parse(texto), expira=ahora + VIGENCIA)
    if estado_http == 429 or estado_http >= 500:
        return Reglas("negar_todo", expira=ahora + VIGENCIA_FALLA, detalle=f"robots.txt respondió {estado_http}")
    return Reglas("permitir_todo", expira=ahora + VIGENCIA, detalle=f"robots.txt respondió {estado_http}")


def agente_de(user_agent: str) -> str:
    """El nombre con el que el robots.txt se refiere a nosotros: 'DocuBot/0.1 (+...)' → 'DocuBot'."""
    return user_agent.split("/", 1)[0].split()[0] if user_agent.strip() else "*"
