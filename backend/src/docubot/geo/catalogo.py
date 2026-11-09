"""Importa un catálogo de lugares (CSV + GeoJSON opcional) a la tabla `lugares`.

CSV: clave, nombre, nivel y, opcionales, padre (clave del lugar que lo
contiene), alias (separados por |), lat, lon. Si un lugar no trae
coordenadas pero sí polígono, su punto es uno que cae dentro del polígono.

Se guarda la huella de los archivos: si no cambiaron, no se vuelve a importar.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Catalogo, Lugar
from docubot.descubrimiento.variables import leer_csv
from docubot.perfiles.esquema import Geografia

log = logging.getLogger("docubot.geo")


@dataclass
class ResultadoImportacion:
    catalogo: str
    lugares: int = 0
    poligonos: int = 0
    sin_cambios: bool = False


def _huella(*rutas: Path | None) -> str:
    h = hashlib.sha256()
    for r in rutas:
        if r is not None:
            h.update(r.read_bytes())
    return h.hexdigest()


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


async def importar(
    sesion: AsyncSession, geografia: Geografia, carpeta: Path, *, forzar: bool = False
) -> ResultadoImportacion:
    nombre = geografia.identificador
    csv_ruta = carpeta / geografia.catalogo
    geo_ruta = carpeta / geografia.poligonos if geografia.poligonos else None
    huella = _huella(csv_ruta, geo_ruta)
    previo = await sesion.get(Catalogo, nombre)
    if previo is not None and previo.huella == huella and not forzar:
        return ResultadoImportacion(nombre, previo.lugares, sin_cambios=True)

    filas = [f for f in leer_csv(csv_ruta) if f.get("clave")]
    for lote in range(0, len(filas), 1000):
        valores = [
            {
                "catalogo": nombre,
                "clave": f["clave"],
                "nombre": f.get("nombre") or f["clave"],
                "nivel": f.get("nivel") or "",
                "alias": [a.strip() for a in (f.get("alias") or "").split("|") if a.strip()],
            }
            for f in filas[lote : lote + 1000]
        ]
        consulta = insert(Lugar).values(valores)
        consulta = consulta.on_conflict_do_update(
            index_elements=["catalogo", "clave"],
            set_={k: consulta.excluded[k] for k in ("nombre", "nivel", "alias")},
        )
        await sesion.execute(consulta)

    ids = {c: i for c, i in await sesion.execute(select(Lugar.clave, Lugar.id).where(Lugar.catalogo == nombre))}
    cambios = []
    for f in filas:
        lat, lon = _float(f.get("lat")), _float(f.get("lon"))
        cambios.append(
            {
                "id": ids[f["clave"]],
                "padre_id": ids.get(f.get("padre") or ""),
                "punto": f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None,
            }
        )
    await sesion.execute(update(Lugar), cambios)

    poligonos = 0
    if geo_ruta is not None:
        datos = json.loads(geo_ruta.read_text(encoding="utf-8"))
        for elemento in datos.get("features", []):
            clave = str((elemento.get("properties") or {}).get(geografia.campo_clave, ""))
            if clave in ids and elemento.get("geometry"):
                await sesion.execute(
                    text("UPDATE lugares SET geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)) WHERE id = :id"),
                    {"g": json.dumps(elemento["geometry"]), "id": ids[clave]},
                )
                poligonos += 1
        await sesion.execute(
            text(
                "UPDATE lugares SET punto = ST_PointOnSurface(geom) WHERE catalogo = :c AND punto IS NULL AND geom IS NOT NULL"
            ),
            {"c": nombre},
        )

    consulta = insert(Catalogo).values(nombre=nombre, huella=huella, lugares=len(filas))
    await sesion.execute(
        consulta.on_conflict_do_update(
            index_elements=["nombre"], set_={"huella": huella, "lugares": len(filas), "actualizado": text("now()")}
        )
    )
    log.info("catálogo %s: %s lugares, %s polígonos", nombre, len(filas), poligonos)
    return ResultadoImportacion(nombre, len(filas), poligonos)
