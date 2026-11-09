"""¿Qué tan bien llena la IA las fichas? Se compara contra un «conjunto dorado».

El conjunto dorado es una carpeta con PDFs y un `dorado.csv`:

    archivo,titulo,fecha_publicacion,instancias,tipo_documento
    plan-tula.pdf,Plan Municipal de Desarrollo 2024-2027,2024-03-05,H. Ayuntamiento|IMPLAN,PMD

- `archivo`: el PDF, relativo a la carpeta.
- Una columna por cada campo de la ficha que quieras medir (las listas, separadas por |).
- `tipo_documento` (opcional): la clave del tipo según el perfil, para medir la clasificación.

Cada campo se compara según su tipo: textos por parecido (≥ 85 %, sin acentos ni
mayúsculas), fechas y números exactos, opciones iguales, listas que compartan al
menos la mitad de sus elementos. Un campo vacío en el CSV cuenta como acierto si
la IA también lo dejó vacío.
"""

import asyncio
import difflib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docubot.ajustes import AjustesIA
from docubot.descubrimiento.variables import leer_csv
from docubot.documentos import pdf
from docubot.filtros.tipos import normalizar
from docubot.ia import fichas as F
from docubot.ia.base import Proveedor
from docubot.perfiles.esquema import Campo, Perfil

PARECIDO = 0.85


@dataclass
class Comparacion:
    campo: str
    esperado: Any
    obtenido: Any
    acierto: bool


@dataclass
class ResultadoDocumento:
    archivo: str
    comparaciones: list[Comparacion] = field(default_factory=list)
    error: str | None = None
    segundos: float = 0.0
    metodo: str = ""


@dataclass
class Informe:
    documentos: list[ResultadoDocumento] = field(default_factory=list)

    def por_campo(self) -> dict[str, dict[str, float]]:
        cuentas: dict[str, list[int]] = {}
        for d in self.documentos:
            for c in d.comparaciones:
                aciertos, total = cuentas.setdefault(c.campo, [0, 0])
                cuentas[c.campo] = [aciertos + c.acierto, total + 1]
        return {k: {"aciertos": a, "total": t, "porcentaje": round(100 * a / t, 1)} for k, (a, t) in cuentas.items()}

    @property
    def global_(self) -> float:
        todas = [c.acierto for d in self.documentos for c in d.comparaciones]
        return round(100 * sum(todas) / len(todas), 1) if todas else 0.0

    def a_dict(self) -> dict[str, Any]:
        return {
            "aciertos": self.global_,
            "por_campo": self.por_campo(),
            "documentos": [
                {
                    "archivo": d.archivo,
                    "metodo": d.metodo,
                    "segundos": d.segundos,
                    "error": d.error,
                    "campos": [
                        {"campo": c.campo, "esperado": c.esperado, "obtenido": c.obtenido, "acierto": c.acierto}
                        for c in d.comparaciones
                    ],
                }
                for d in self.documentos
            ],
        }


def _vacio(v: Any) -> bool:
    return v in (None, "", [])


def comparar(campo: Campo | None, esperado: str, obtenido: Any) -> bool:
    if not esperado.strip():
        return _vacio(obtenido)
    if _vacio(obtenido):
        return False
    tipo = campo.tipo if campo else "texto"
    if tipo == "fecha":
        return F.fecha(esperado) == obtenido
    if tipo == "numero":
        try:
            return abs(float(esperado.replace(",", "")) - float(obtenido)) < 1e-9
        except (TypeError, ValueError):
            return False
    if tipo == "lista":
        a = {normalizar(x) for x in esperado.split("|") if x.strip()}
        b = {normalizar(str(x)) for x in (obtenido if isinstance(obtenido, list) else [obtenido])}
        return bool(a | b) and len(a & b) / len(a | b) >= 0.5
    if tipo == "opcion":
        return normalizar(esperado) == normalizar(str(obtenido))
    return difflib.SequenceMatcher(None, normalizar(esperado), normalizar(str(obtenido))).ratio() >= PARECIDO


async def evaluar(perfil: Perfil, carpeta: Path, proveedor: Proveedor, ajustes: AjustesIA) -> Informe:
    filas = leer_csv(carpeta / "dorado.csv")
    if not filas or "archivo" not in filas[0]:
        raise ValueError(f"{carpeta / 'dorado.csv'} necesita una columna «archivo» y al menos una fila")
    columnas = [c for c in filas[0] if c != "archivo"]
    sistema = F.instrucciones(perfil)
    informe = Informe()
    for fila in filas:
        r = ResultadoDocumento(fila["archivo"])
        informe.documentos.append(r)
        ruta = carpeta / fila["archivo"]
        e = await asyncio.to_thread(pdf.extraer, ruta)
        imagenes: list[str] = []
        if e.estado == "texto":
            r.metodo = "texto"
            usuario = F.entrada_texto(e.para_ia(ajustes.paginas, ajustes.max_caracteres))
        elif e.estado == "escaneado" and proveedor.vision and ajustes.vision:
            r.metodo = "imagen"
            imagenes = await asyncio.to_thread(pdf.imagenes, ruta, ajustes.paginas_imagen)
            usuario = F.entrada_imagenes(len(imagenes))
        else:
            r.error = e.error or "escaneado y el proveedor no lee imágenes"
            continue
        inicio = time.monotonic()
        try:
            respuesta = await proveedor.completar(sistema, usuario, imagenes)
        except Exception as error:
            r.error = f"{type(error).__name__}: {error}"
            continue
        r.segundos = round(time.monotonic() - inicio, 1)
        datos = F.json_laxo(respuesta.texto) or {}
        v = F.validar(datos, perfil, e.contenido if r.metodo == "texto" else "")
        for columna in columnas:
            esperado = fila.get(columna, "")
            if columna == "tipo_documento":
                obtenido = v.tipo_ia
                r.comparaciones.append(Comparacion(columna, esperado, obtenido, (esperado or None) == obtenido))
            elif columna in perfil.fichas.campos:
                obtenido = v.campos.get(columna)
                r.comparaciones.append(
                    Comparacion(
                        columna, esperado, obtenido, comparar(perfil.fichas.campos[columna], esperado, obtenido)
                    )
                )
    return informe
