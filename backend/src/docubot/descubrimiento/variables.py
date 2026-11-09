"""Variables de las consultas: combinaciones de listas o filas de un CSV."""

import csv
import itertools
from pathlib import Path

from docubot.perfiles.esquema import MARCADOR, FuenteBuscador


def leer_csv(ruta: Path) -> list[dict[str, str]]:
    """Filas de un CSV como diccionarios (acepta coma, punto y coma o tabulador)."""
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        muestra = f.read(8192)
        f.seek(0)
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
        except csv.Error:
            dialecto = csv.excel
        lector = csv.DictReader(f, dialect=dialecto)
        return [{(k or "").strip(): (v or "").strip() for k, v in fila.items() if k is not None} for fila in lector]


def filas(fuente: FuenteBuscador, carpeta: Path) -> list[dict[str, str]]:
    if fuente.variables is None:
        return [{}]
    if isinstance(fuente.variables, str):
        return leer_csv(carpeta / fuente.variables)
    nombres = list(fuente.variables)
    return [
        dict(zip(nombres, combinacion, strict=True)) for combinacion in itertools.product(*fuente.variables.values())
    ]


def formatear(consulta: str, fila: dict[str, str]) -> str:
    return " ".join(MARCADOR.sub(lambda m: fila.get(m.group(1), ""), consulta).split())


def consultas(fuente: FuenteBuscador, carpeta: Path) -> list[tuple[str, str | None]]:
    """(consulta, clave de lugar) para cada fila y cada plantilla, sin repetir."""
    salida: dict[str, str | None] = {}
    for fila in filas(fuente, carpeta):
        lugar = fila.get(fuente.columna_lugar) if fuente.columna_lugar else None
        for plantilla in fuente.consultas:
            texto = formatear(plantilla, fila)
            if texto and texto not in salida:
                salida[texto] = lugar or None
    return list(salida.items())
