"""Buscar en los documentos: por palabras, por tema o las dos combinadas.

- Palabras: texto completo de Postgres en español y sin acentos. La ficha
  (sobre todo su título) pesa más que el cuerpo. Admite la sintaxis de un
  buscador web: "frase exacta", palabra -excluida, a OR b.
- Tema: los fragmentos del documento más parecidos (vectores) a la consulta,
  aunque no compartan palabras.
- Mixta: las dos listas se combinan por posición (Reciprocal Rank Fusion).

Cada resultado trae los pasajes que coinciden, con su página.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.ajustes import obtener_ajustes
from docubot.busqueda import embeddings

MARCA_INICIO, MARCA_FIN = "⟦", "⟧"  # la interfaz las vuelve resaltado (el resto del texto se escapa)
SEPARADOR = " ⁞ "
CANDIDATOS = 300  # cuántos resultados de cada búsqueda entran a la mezcla
RRF = 60


@dataclass
class Coincidencia:
    texto: str
    pagina: int | None
    tipo: str  # palabras | tema


@dataclass
class Resultado:
    documento_id: int
    puntaje: float
    coincidencias: list[Coincidencia] = field(default_factory=list)


SINTAXIS = re.compile(r'"|(^|\s)-\w|OR')


def expresion_consulta(q: str) -> str:
    """SQL de la consulta de texto completo.

    Con sintaxis de buscador ("frase", -excluida, OR) se respeta tal cual. Si no,
    basta con que coincidan algunas palabras (los que tienen todas puntúan más):
    pedirlas todas deja fuera documentos buenos que no usan una de ellas.
    """
    if SINTAXIS.search(q):
        return "websearch_to_tsquery('docubot_es', :q)"
    return "replace(websearch_to_tsquery('docubot_es', :q)::text, ' & ', ' | ')::tsquery"


async def por_palabras(sesion: AsyncSession, q: str, ids: list[int] | None) -> list[tuple[int, float]]:
    filtro = "AND documento_id = ANY(:ids)" if ids is not None else ""
    filas = await sesion.execute(
        text(
            f"""
            WITH consulta AS (SELECT {expresion_consulta(q)} AS c),
            en_texto AS (
              SELECT documento_id, ts_rank_cd(tsv, c, 32) AS r FROM textos, consulta WHERE tsv @@ c {filtro}
            ),
            en_ficha AS (
              SELECT documento_id, max(ts_rank(tsv, c)) AS r FROM fichas, consulta WHERE tsv @@ c {filtro}
              GROUP BY documento_id
            )
            SELECT documento_id, sum(r) AS puntaje FROM (
              SELECT documento_id, r FROM en_texto
              UNION ALL
              SELECT documento_id, 2 * r FROM en_ficha
            ) x
            GROUP BY documento_id
            ORDER BY puntaje DESC, documento_id DESC
            LIMIT :limite
            """
        ),
        {"q": q, "ids": ids, "limite": 5000},
    )
    return [(d, float(p)) for d, p in filas]


async def por_tema(
    sesion: AsyncSession, q: str, ids: list[int] | None
) -> tuple[list[tuple[int, float]], dict[int, Coincidencia]]:
    proveedor = embeddings.obtener()
    vector = await proveedor.consulta(q)
    filtro = "AND documento_id = ANY(:ids)" if ids is not None else ""
    filas = await sesion.execute(
        text(
            f"""
            SELECT documento_id, pagina, texto, 1 - (embedding <=> CAST(:v AS vector)) AS similitud
            FROM fragmentos
            WHERE modelo = :modelo {filtro}
            ORDER BY embedding <=> CAST(:v AS vector)
            LIMIT :limite
            """
        ),
        {"v": "[" + ",".join(map(str, vector)) + "]", "modelo": proveedor.modelo, "ids": ids, "limite": CANDIDATOS * 4},
    )
    mejores: dict[int, tuple[float, Coincidencia]] = {}
    for documento_id, pagina, texto_, similitud in filas:
        if documento_id not in mejores:  # vienen ordenados: el primero es el mejor fragmento del documento
            mejores[documento_id] = (float(similitud), Coincidencia(_recorte(texto_), pagina, "tema"))
    orden = sorted(mejores.items(), key=lambda x: -x[1][0])[:CANDIDATOS]
    # todo se parece un poco a todo: solo lo bastante parecido y cerca del mejor resultado
    a = obtener_ajustes().busqueda
    if orden:
        corte = max(a.similitud_minima, orden[0][1][0] - a.ventana_similitud)
        orden = [x for x in orden if x[1][0] >= corte]
    return [(d, s) for d, (s, _) in orden], {d: c for d, (_, c) in orden}


def _recorte(texto_: str, largo: int = 280) -> str:
    texto_ = " ".join(texto_.split())
    return texto_ if len(texto_) <= largo else texto_[:largo].rsplit(" ", 1)[0] + "…"


def mezclar(*listas: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: suma 1/(60 + posición) de cada lista."""
    puntos: dict[int, float] = {}
    for lista in listas:
        for posicion, (documento_id, _) in enumerate(lista[:CANDIDATOS]):
            puntos[documento_id] = puntos.get(documento_id, 0.0) + 1.0 / (RRF + posicion + 1)
    return sorted(puntos.items(), key=lambda x: -x[1])


async def pasajes(sesion: AsyncSession, q: str, ids: list[int]) -> dict[int, list[Coincidencia]]:
    """Los pasajes del texto que coinciden con la consulta, resaltados y con su página."""
    if not ids:
        return {}
    filas = (
        await sesion.execute(
            text(
                f"""
                SELECT documento_id,
                       ts_headline('docubot_es', left(contenido, 300000), {expresion_consulta(q)},
                         'MaxFragments=2, MinWords=12, MaxWords=32, FragmentDelimiter="{SEPARADOR}",
                          StartSel="{MARCA_INICIO}", StopSel="{MARCA_FIN}"')
                FROM textos WHERE documento_id = ANY(:ids) AND tsv @@ {expresion_consulta(q)}
                """
            ),
            {"q": q, "ids": ids},
        )
    ).all()
    trozos: list[tuple[int, str]] = []
    for documento_id, encabezado in filas:
        for trozo in (encabezado or "").split(SEPARADOR):
            if MARCA_INICIO in trozo:
                trozos.append((documento_id, trozo.strip()))
    if not trozos:
        return {}
    # la página de cada pasaje: el último «[página N]» antes de la primera palabra resaltada
    buscados = [re.sub(f"[{MARCA_INICIO}{MARCA_FIN}]", "", t[t.index(MARCA_INICIO) :])[:50] for _, t in trozos]
    paginas = (
        await sesion.execute(
            text(
                """
                SELECT x.i, (regexp_match(left(t.contenido, strpos(t.contenido, x.frag)), '.*\\[página (\\d+)\\]'))[1]
                FROM unnest(CAST(:docs AS bigint[]), CAST(:frags AS text[])) WITH ORDINALITY AS x(doc, frag, i)
                JOIN textos t ON t.documento_id = x.doc
                """
            ),
            {"docs": [d for d, _ in trozos], "frags": buscados},
        )
    ).all()
    pagina_de = {int(i): (int(p) if p else None) for i, p in paginas}
    salida: dict[int, list[Coincidencia]] = {}
    for i, (documento_id, trozo) in enumerate(trozos, 1):
        limpio = " ".join(re.sub(r"\[?página \d+\]", " ", trozo).split())  # también un «página 1]» cortado
        salida.setdefault(documento_id, []).append(Coincidencia(limpio, pagina_de.get(i), "palabras"))
    return salida


async def buscar(
    sesion: AsyncSession, q: str, modo: str, ids: list[int] | None, limite: int, desde: int
) -> tuple[str, int, list[Resultado]]:
    """(modo usado, total, resultados de la página)."""
    tema_posible = embeddings.activo()
    if modo == "mixta" and not tema_posible:
        modo = "palabras"
    if modo == "tema" and not tema_posible:
        raise ValueError("la búsqueda por tema está apagada (busqueda.embeddings en config/docubot.yaml)")

    tema_coincidencias: dict[int, Coincidencia] = {}
    if modo == "palabras":
        orden = await por_palabras(sesion, q, ids)
    elif modo == "tema":
        orden, tema_coincidencias = await por_tema(sesion, q, ids)
    else:
        palabras = await por_palabras(sesion, q, ids)
        tema, tema_coincidencias = await por_tema(sesion, q, ids)
        orden = mezclar(palabras, tema)

    pagina = orden[desde : desde + limite]
    ids_pagina = [d for d, _ in pagina]
    con_palabras = await pasajes(sesion, q, ids_pagina) if modo != "tema" else {}
    resultados = []
    for documento_id, puntaje in pagina:
        coincidencias = list(con_palabras.get(documento_id, []))
        if documento_id in tema_coincidencias and len(coincidencias) < 2:
            coincidencias.append(tema_coincidencias[documento_id])
        resultados.append(Resultado(documento_id, round(puntaje, 4), coincidencias))
    return modo, len(orden), resultados


def a_dict(r: Resultado) -> dict[str, Any]:
    return {
        "puntaje": r.puntaje,
        "coincidencias": [{"texto": c.texto, "pagina": c.pagina, "tipo": c.tipo} for c in r.coincidencias],
    }
