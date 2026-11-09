"""Geografía: catálogo, desambiguación de nombres repetidos, ubicación y mapa."""

import json
import textwrap

import httpx
import pytest
from sqlalchemy import func, select
from test_corridas import crear, vaciar_cola, web  # noqa: F401
from test_descarga import ETAPAS, almacen  # noqa: F401
from test_fichar import ia_falsa, sitio  # noqa: F401

from docubot.db.modelos import DocumentoLugar, Lugar
from docubot.geo.catalogo import importar
from docubot.geo.coincidencias import EntradaLugar, Indice, buscar
from docubot.geo.ubicar import decidir
from docubot.main import app
from docubot.perfiles import cargar
from docubot.perfiles.esquema import Geografia

CATALOGO = """clave,nombre,nivel,padre,alias,lat,lon
13,Hidalgo,estado,,,,
16,Michoacán de Ocampo,estado,,Michoacán,,
21,Puebla,estado,,,,
23,Quintana Roo,estado,,Q. Roo,,
13003,Actopan,municipio,13,,20.27,-98.94
13048,Pachuca de Soto,municipio,13,Pachuca,20.12,-98.73
13077,Tulancingo de Bravo,municipio,13,Tulancingo,20.08,-98.36
16034,Hidalgo,municipio,16,Ciudad Hidalgo,19.69,-100.55
21114,Puebla,municipio,21,,19.04,-98.2
21032,Benito Juárez,municipio,21,,19.5,-97.6
23005,Benito Juárez,municipio,23,Cancún,21.16,-86.82
07,Chiapas,estado,,,,
07059,Reforma,municipio,07,,17.87,-93.15
"""


def cuadro(x: float, y: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]]}


def escribir_catalogo(carpeta) -> Geografia:
    (carpeta / "lugares.csv").write_text(CATALOGO, encoding="utf-8")
    (carpeta / "lugares.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"cve": "13"}, "geometry": cuadro(-99.5, 19.5)},
                    {"type": "Feature", "properties": {"cve": "13077"}, "geometry": cuadro(-98.5, 20)},
                ],
            }
        ),
        encoding="utf-8",
    )
    return Geografia.model_validate(
        {"catalogo": "lugares.csv", "poligonos": "lugares.geojson", "campo_clave": "cve", "nombre": "prueba"},
        context={"carpeta": carpeta},
    )


def indice() -> Indice:
    lugares, alias, ids = [], {}, {}
    filas = [l.split(",") for l in CATALOGO.strip().splitlines()[1:]]
    for i, (clave, *_rest) in enumerate(filas, 1):
        ids[clave] = i
    for i, (clave, nombre, nivel, padre, al, *_r) in enumerate(filas, 1):
        lugares.append(EntradaLugar(i, clave, nombre, nivel, ids.get(padre)))
        alias[i] = [a for a in al.split("|") if a]
    return Indice(lugares, alias)


def clave(r) -> str | None:
    return r.lugar.clave if r.lugar else None


async def test_importar_catalogo(tmp_path, sesiones):
    geo = escribir_catalogo(tmp_path)
    async with sesiones() as s:
        r = await importar(s, geo, tmp_path)
        await s.commit()
        assert (r.lugares, r.poligonos, r.sin_cambios) == (13, 2, False)
        tulancingo = await s.scalar(select(Lugar).where(Lugar.clave == "13077"))
        hidalgo = await s.scalar(select(Lugar).where(Lugar.clave == "13"))
        assert tulancingo.padre_id == hidalgo.id and tulancingo.alias == ["Tulancingo"]
        assert await s.scalar(select(func.ST_X(Lugar.punto)).where(Lugar.clave == "13077")) == pytest.approx(-98.36)
        # el estado no trae coordenadas: su punto cae dentro de su polígono
        assert await s.scalar(select(func.ST_Within(Lugar.punto, Lugar.geom)).where(Lugar.clave == "13"))

        assert (await importar(s, geo, tmp_path)).sin_cambios
        (tmp_path / "lugares.csv").write_text(CATALOGO + "13999,Nuevo,municipio,13,,,\n", encoding="utf-8")
        r = await importar(s, geo, tmp_path)
        assert r.lugares == 14 and not r.sin_cambios


def test_desambiguacion():
    i = indice()
    assert clave(buscar(i, "H. Ayuntamiento de Benito Juárez, Quintana Roo")) == "23005"
    assert clave(buscar(i, "Publicado en 2023.", titulo="Bando de policía y gobierno de Cancún")) == "23005"
    # una palabra común repetida en el cuerpo no gana por volumen
    assert buscar(i, "Se publica la reforma. " * 20 + "Tulancingo").estado == "sin_lugar"
    # el municipio que se nombra de pasada no le gana al estado del título
    r = buscar(
        i, "Diputados de Pachuca de Soto y otros distritos.", titulo="Reglamento del Congreso del Estado de Hidalgo"
    )
    assert clave(r) == "13"
    ambiguo = buscar(i, "Reglamento de tránsito del municipio de Benito Juárez")
    assert ambiguo.estado == "ambiguo" and {c.lugar.clave for c in ambiguo.candidatos[:2]} == {"21032", "23005"}

    assert clave(buscar(i, "Programa de Desarrollo Urbano del Estado de Hidalgo")) == "13"
    assert clave(buscar(i, "Atlas de riesgos del municipio de Hidalgo, Michoacán")) == "16034"
    assert clave(buscar(i, "Gobierno del Estado de Puebla. Plan estatal")) == "21"
    assert clave(buscar(i, "H. Ayuntamiento del municipio de Puebla")) == "21114"
    assert clave(buscar(i, "texto sin lugar", titulo="Plan Municipal de Desarrollo de Tulancingo de Bravo")) == "13077"
    assert clave(buscar(i, "nada", lugar_ia="Actopan, Hidalgo")) == "13003"
    assert buscar(i, "Un documento sin lugares conocidos").estado == "sin_lugar"
    # «Benito Juárez» no se cuenta además como otro lugar
    assert len(i.menciones("Benito Juárez")) == 1


def test_decidir_cruza_fuente_y_contenido():
    i = indice()
    u = decidir(i, "13077", "Plan municipal de Tulancingo")
    assert (u.origen, u.confianza, u.estado) == ("fuente+contenido", 1.0, "asignado")
    u = decidir(i, "13077", "Reglamento interior")
    assert (u.origen, u.confianza, u.estado) == ("fuente", 0.85, "asignado")
    u = decidir(i, "13077", "Municipio de Pachuca de Soto, Hidalgo. H. Ayuntamiento de Pachuca de Soto")
    assert u.estado == "revision" and {c["clave"] for c in u.candidatos} >= {"13077", "13048"}
    u = decidir(i, None, "municipio de Benito Juárez")
    assert u.lugar_id is None and u.estado == "ambiguo" and len(u.candidatos) >= 2


async def test_ubicar_y_mapa(tmp_path, sesiones, web, almacen, ia_falsa):
    escribir_catalogo(tmp_path)
    sitio(web)
    (tmp_path / "geo.yaml").write_text(
        textwrap.dedent("""
        nombre: geo
        descubrimiento:
          fuentes:
            - tipo: semillas
              urls: [https://m.gob.mx/]
          exploracion: {sitemap: false, profundidad: 1}
        documentos:
          tipos:
            PLAN: {nombre: Plan, palabras: [plan]}
        fichas:
          campos:
            titulo: {tipo: texto, requerido: true}
        geografia: {catalogo: lugares.csv, poligonos: lugares.geojson, campo_clave: cve, nombre: prueba}
        red:
          peticiones_por_segundo_por_dominio: 1000
    """),
        encoding="utf-8",
    )
    cargado = cargar(tmp_path / "geo.yaml")
    assert cargado.valido, cargado.errores
    await crear(sesiones, cargado, descargar=True)
    await vaciar_cola(sesiones, ETAPAS + ("ubicar",))

    async with sesiones() as s:
        filas = (
            await s.execute(select(DocumentoLugar, Lugar.clave).outerjoin(Lugar, Lugar.id == DocumentoLugar.lugar_id))
        ).all()
    por_estado = {dl.estado: (dl, c) for dl, c in filas}
    assert set(por_estado) == {"asignado", "sin_lugar"}
    asignado, clave_asignada = por_estado["asignado"]
    assert clave_asignada == "13003" and asignado.origen == "contenido"  # «H. Ayuntamiento de Actopan» en el PDF

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
        m = (await api.get("/api/mapa", params={"perfil": "geo"})).json()
        assert m["catalogo"] == "prueba" and m["documentos"] == 2
        assert [(l["clave"], l["documentos"], l["padre"]) for l in m["lugares"]] == [("13003", 1, "Hidalgo")]
        assert m["por_estado"] == {"asignado": 1, "sin_lugar": 1}

        g = (await api.get("/api/mapa/poligonos", params={"catalogo": "prueba", "nivel": "estado"})).json()
        assert [f["properties"]["clave"] for f in g["features"]] == ["13"]
        niveles = (await api.get("/api/mapa/niveles", params={"catalogo": "prueba"})).json()
        assert [n["nivel"] for n in niveles] == ["estado", "municipio"]

        async with sesiones() as s:
            hidalgo = await s.scalar(select(Lugar.id).where(Lugar.clave == "13"))
            tulancingo = await s.scalar(select(Lugar.id).where(Lugar.clave == "13077"))
        # filtrar por el estado incluye sus municipios
        assert (await api.get("/api/documentos", params={"lugar": hidalgo})).json()["total"] == 1

        assert [
            x["clave"]
            for x in (await api.get("/api/lugares/buscar", params={"catalogo": "prueba", "q": "tulan"})).json()
        ] == ["13077"]
        sin_lugar = por_estado["sin_lugar"][0].documento_id
        r = await api.put(f"/api/documentos/{sin_lugar}/lugar", json={"lugar_id": tulancingo})
        assert r.json()["nombre"] == "Tulancingo de Bravo"
        d = (await api.get(f"/api/documentos/{sin_lugar}")).json()
        assert [(l["nombre"], l["origen"], l["padre"]) for l in d["lugares"]] == [
            ("Tulancingo de Bravo", "manual", "Hidalgo")
        ]
        assert (await api.get("/api/lugares/dudosos")).json()["total"] == 0
