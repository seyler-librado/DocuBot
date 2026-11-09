"""Búsqueda por palabras (texto completo en español), por tema (vectores) y mixta."""

import math

import httpx
import pytest
from sqlalchemy import func, select

from docubot.ajustes import AjustesBusqueda
from docubot.busqueda import embeddings
from docubot.busqueda.buscar import mezclar
from docubot.busqueda.embeddings import ProveedorEmbeddings
from docubot.busqueda.fragmentos import partir
from docubot.db.modelos import Candidato, Documento, Ficha, Fragmento, Perfil, Tarea, Texto
from docubot.main import app
from docubot.pipeline import cola
from docubot.pipeline.etapas import ETAPAS
from docubot.pipeline.trabajador import procesar_una

# grupos de palabras que «significan lo mismo» para el modelo simulado
TEMAS = [
    {"transito", "vialidad", "vehiculos", "manejar", "conducir", "automoviles", "movilidad"},
    {"agua", "drenaje", "potable", "saneamiento", "alcantarillado"},
    {"riesgo", "inundacion", "sismo", "proteccion", "civil", "desastres"},
]


class VectoresFalsos(ProveedorEmbeddings):
    nombre = "falso"

    def __init__(self):
        super().__init__(AjustesBusqueda(embeddings="local", modelo="falso-3"))

    async def _vectores(self, textos, extra=(0.01, 0.0)):
        from docubot.filtros.tipos import normalizar

        salida = []
        for t in textos:
            palabras = set(normalizar(t).split())
            v = [float(len(palabras & tema)) for tema in TEMAS] + list(extra)
            norma = math.sqrt(sum(x * x for x in v))
            salida.append([x / norma for x in v])
        return salida

    async def consulta(self, texto):
        # una dimensión propia para las consultas: lo que no toca ningún tema no se parece a nada
        return (await self._vectores([texto], extra=(0.0, 0.01)))[0]


def contenido(*paginas: str) -> str:
    return "".join(f"\n\n[página {i}]\n{t}" for i, t in enumerate(paginas, 1)).strip()


DOCS = {
    "transito": (
        "Reglamento de Tránsito",
        contenido(
            "Disposiciones generales del municipio.",
            "Capítulo segundo sobre la circulación.",
            "Los vehículos automotores deberán respetar los límites de velocidad en la vialidad urbana.",
        ),
    ),
    "agua": (
        "Reglamento del Organismo de Agua Potable",
        contenido("Servicio de drenaje y alcantarillado sanitario del municipio."),
    ),
    "planeacion": (
        "Programa Municipal",
        contenido("Lineamientos de la Planeación urbana y la zonificación del territorio."),
    ),
    "movilidad_cuerpo": (
        "Informe anual",
        contenido("Se mencionó la movilidad una sola vez en este informe de actividades."),
    ),
    "movilidad_titulo": (
        "Reglamento de Movilidad Sustentable",
        contenido("Normas generales para peatones y ciclistas."),
    ),
}


@pytest.fixture
async def corpus(sesiones):
    ids = {}
    async with sesiones() as s:
        perfil = Perfil(nombre="busqueda", config={})
        otro = Perfil(nombre="otro", config={})
        s.add_all([perfil, otro])
        await s.flush()
        for i, (clave, (titulo, texto)) in enumerate(DOCS.items()):
            d = Documento(sha256=f"{i:064d}", ruta=f"x/{i}.pdf", bytes=100, mime="application/pdf")
            s.add(d)
            await s.flush()
            ids[clave] = d.id
            s.add(Texto(documento_id=d.id, contenido=texto, metodo="texto", caracteres=len(texto)))
            s.add(Ficha(documento_id=d.id, perfil_id=perfil.id, campos={"titulo": titulo}, estado="ok"))
            s.add(
                Candidato(
                    perfil_id=(otro if clave == "agua" else perfil).id,
                    url=f"https://m.gob.mx/{clave}.pdf",
                    clave_url=f"m.gob.mx/{clave}.pdf",
                    fuente="semillas",
                    estado="descargado",
                    documento_id=d.id,
                )
            )
        await s.commit()
    return ids


@pytest.fixture
def api():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def buscar(api, q, **params):
    r = await api.get("/api/buscar", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()


async def test_palabras_en_espanol_sin_acentos(corpus, api):
    r = await buscar(api, "planeacion", modo="palabras")
    assert r["modo"] == "palabras" and [d["id"] for d in r["elementos"]] == [corpus["planeacion"]]
    # raíces: «reglamentos» encuentra «Reglamento»
    r = await buscar(api, "reglamentos", modo="palabras")
    assert set(d["id"] for d in r["elementos"]) == {corpus["transito"], corpus["agua"], corpus["movilidad_titulo"]}
    # el título de la ficha pesa más que una mención en el cuerpo
    r = await buscar(api, "movilidad", modo="palabras")
    assert [d["id"] for d in r["elementos"]][:2] == [corpus["movilidad_titulo"], corpus["movilidad_cuerpo"]]
    # sintaxis de buscador
    r = await buscar(api, "reglamento -agua", modo="palabras")
    assert corpus["agua"] not in [d["id"] for d in r["elementos"]]
    r = await buscar(api, '"agua potable"', modo="palabras")
    assert [d["id"] for d in r["elementos"]] == [corpus["agua"]]
    # sin sintaxis, basta con algunas palabras; las que tienen todas van primero
    r = await buscar(api, "planeacion urbana arboles", modo="palabras")
    assert r["elementos"][0]["id"] == corpus["planeacion"]  # el de tránsito también dice «urbana»
    r = await buscar(api, "reglamento agua", modo="palabras")
    assert r["elementos"][0]["id"] == corpus["agua"] and r["total"] == 3


async def test_pasajes_resaltados_con_pagina(corpus, api):
    r = await buscar(api, "vehiculos", modo="palabras")
    [d] = r["elementos"]
    [c] = d["coincidencias"]
    assert c["pagina"] == 3 and c["tipo"] == "palabras"
    assert "⟦vehículos⟧" in c["texto"]
    assert d["titulo"] == "Reglamento de Tránsito"  # trae el resumen del documento


async def test_filtros(corpus, api):
    assert (await buscar(api, "reglamento", modo="palabras", perfil="otro"))["total"] == 1
    assert (await buscar(api, "reglamento", modo="palabras", perfil="busqueda"))["total"] == 2


async def test_tema_y_mixta(corpus, api, sesiones):
    # sin vectores, mixta se vuelve palabras y tema avisa
    assert (await buscar(api, "manejar", modo="mixta"))["modo"] == "palabras"
    assert (await api.get("/api/buscar", params={"q": "manejar", "modo": "tema"})).status_code == 422

    embeddings.usar_proveedor(VectoresFalsos())
    try:
        # indexar con la etapa (encola lo que falta)
        assert (await api.post("/api/busqueda/indexar")).json() == {"encolados": 5}
        while True:
            async with sesiones() as s:
                tareas = await cola.tomar(s, "indexar", "prueba")
                await s.commit()
            if not tareas:
                break
            await procesar_una(ETAPAS["indexar"], tareas[0], sesiones)
        estado = (await api.get("/api/busqueda/estado")).json()
        assert estado["tema"]["documentos"] == 5 and estado["tema"]["faltan"] == 0

        # «reglas para conducir» no comparte palabras con el reglamento de tránsito, pero sí tema
        r = await buscar(api, "reglas para conducir automoviles", modo="tema")
        assert r["modo"] == "tema" and r["elementos"][0]["id"] == corpus["transito"]
        assert r["elementos"][0]["coincidencias"][0]["tipo"] == "tema"
        assert (await buscar(api, "reglas para conducir automoviles", modo="palabras"))["total"] == 0

        # lo que no se parece a nada no devuelve «todo»
        assert (await buscar(api, "receta de pastel", modo="tema"))["total"] == 0
        r = await buscar(api, "drenaje", modo="mixta")
        assert r["modo"] == "mixta" and r["elementos"][0]["id"] == corpus["agua"]
    finally:
        embeddings.usar_proveedor(None)


def test_mezcla_por_posicion():
    assert [d for d, _ in mezclar([(1, 9.0), (2, 5.0)], [(2, 0.9), (3, 0.8)])] == [2, 1, 3]


def test_partir_en_fragmentos():
    texto = contenido("palabra " * 300, "", "otra página con texto suficiente para un fragmento propio")
    pedazos = partir(texto, tamano=500, solape=100)
    assert {p.pagina for p in pedazos} == {1, 3}
    assert all(len(p.texto) <= 500 for p in pedazos)
    assert [p.orden for p in pedazos] == list(range(len(pedazos)))
    assert len(partir(texto, tamano=500, solape=100, maximo=2)) == 2


async def test_extraer_encola_indexado(tmp_path, sesiones, monkeypatch):
    """Con búsqueda por tema activa, cada documento extraído se encola para indexar."""
    from simulado import pdf_con_texto

    from docubot.ajustes import obtener_ajustes

    carpeta = tmp_path / "almacen"
    (carpeta / "ab").mkdir(parents=True)
    (carpeta / "ab" / "doc.pdf").write_bytes(pdf_con_texto(["Reglamento de tránsito " * 20]))
    monkeypatch.setenv("DOCUBOT_ALMACEN__CARPETA", str(carpeta))
    obtener_ajustes.cache_clear()
    embeddings.usar_proveedor(VectoresFalsos())
    try:
        async with sesiones() as s:
            d = Documento(sha256="f" * 64, ruta="ab/doc.pdf", bytes=1, mime="application/pdf")
            s.add(d)
            await s.flush()
            await cola.encolar(s, "extraer", {"documento_id": d.id})
            await s.commit()
            [t] = await cola.tomar(s, "extraer", "prueba")
            await s.commit()
        await procesar_una(ETAPAS["extraer"], t, sesiones)
        async with sesiones() as s:
            assert await s.scalar(select(func.count()).where(Tarea.etapa == "indexar"))
            [t] = await cola.tomar(s, "indexar", "prueba")
            await s.commit()
        await procesar_una(ETAPAS["indexar"], t, sesiones)
        async with sesiones() as s:
            assert await s.scalar(select(func.count()).select_from(Fragmento)) >= 1
    finally:
        embeddings.usar_proveedor(None)
        obtener_ajustes.cache_clear()
