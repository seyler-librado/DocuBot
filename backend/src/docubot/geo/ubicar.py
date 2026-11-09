"""Dónde aplica un documento: se cruzan la fuente y el contenido.

| fuente (fila/dominio) | contenido                         | resultado                                  |
|-----------------------|-----------------------------------|--------------------------------------------|
| L                     | coincide o menciona L             | L, origen «fuente+contenido», confianza 1  |
| L                     | nada                              | L, origen «fuente», confianza 0.85         |
| L                     | otro lugar con fuerza, L ni se menciona | L en «revision», con ambos candidatos |
| —                     | asigna M                          | M, origen «contenido»                      |
| —                     | ambiguo                           | sin lugar, «ambiguo», con los candidatos   |
| —                     | nada                              | sin lugar, «sin_lugar»                     |
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Catalogo, Lugar
from docubot.geo.coincidencias import EntradaLugar, Indice, Resultado, buscar

_indices: dict[tuple[str, str], Indice] = {}


async def indice_de(sesion: AsyncSession, catalogo: str) -> Indice | None:
    fila = await sesion.get(Catalogo, catalogo)
    if fila is None:
        return None
    clave = (catalogo, fila.huella)
    if clave not in _indices:
        filas = (
            await sesion.execute(
                select(Lugar.id, Lugar.clave, Lugar.nombre, Lugar.nivel, Lugar.padre_id, Lugar.alias).where(
                    Lugar.catalogo == catalogo
                )
            )
        ).all()
        _indices[clave] = Indice(
            [EntradaLugar(i, c, n, nv, p) for i, c, n, nv, p, _ in filas],
            {i: list(a or []) for i, _, _, _, _, a in filas},
        )
    return _indices[clave]


@dataclass
class Ubicacion:
    lugar_id: int | None
    origen: str
    confianza: float
    estado: str  # asignado | ambiguo | revision
    candidatos: list[dict[str, Any]] = field(default_factory=list)


def _lista(resultado: Resultado, indice: Indice, extra: list[EntradaLugar] = ()) -> list[dict[str, Any]]:
    vistos, salida = set(), []
    for lugar, puntaje in [(e, None) for e in extra] + [(c.lugar, c.puntaje) for c in resultado.candidatos]:
        if lugar.id in vistos:
            continue
        vistos.add(lugar.id)
        padre = indice.por_id.get(lugar.padre_id) if lugar.padre_id else None
        salida.append(
            {
                "id": lugar.id,
                "clave": lugar.clave,
                "nombre": lugar.nombre,
                "nivel": lugar.nivel,
                "padre": padre.nombre if padre else None,
                "puntaje": puntaje,
            }
        )
    return salida[:6]


def decidir(indice: Indice, clave_fuente: str | None, texto: str, titulo: str = "", lugar_ia: str = "") -> Ubicacion:
    resultado = buscar(indice, texto, titulo=titulo, lugar_ia=lugar_ia)
    fuente = next((l for l in indice.por_id.values() if l.clave == clave_fuente), None) if clave_fuente else None

    if fuente is not None:
        menciona = resultado.puntaje_de(fuente.id) > 0
        if resultado.lugar is not None and resultado.lugar.id == fuente.id or menciona:
            return Ubicacion(fuente.id, "fuente+contenido", 1.0, "asignado", _lista(resultado, indice, [fuente]))
        otro = resultado.lugar
        if (
            otro is not None
            and resultado.confianza >= 0.7
            and otro.profundidad >= fuente.profundidad
            and otro.id not in indice.descendientes(fuente.id)
        ):
            return Ubicacion(fuente.id, "fuente", 0.5, "revision", _lista(resultado, indice, [fuente]))
        return Ubicacion(fuente.id, "fuente", 0.85, "asignado", _lista(resultado, indice, [fuente]))

    if resultado.estado == "asignado" and resultado.lugar is not None:
        return Ubicacion(resultado.lugar.id, "contenido", resultado.confianza, "asignado", _lista(resultado, indice))
    if resultado.estado == "ambiguo":
        return Ubicacion(None, "contenido", 0.0, "ambiguo", _lista(resultado, indice))
    return Ubicacion(None, "contenido", 0.0, "sin_lugar", _lista(resultado, indice))
