"""API de la interfaz: biblioteca, fichas, revisión, candidatos, corridas con ajustes y eventos."""

import asyncio
import json

import httpx
import psycopg
import pytest
from conftest import URL_PRUEBAS
from sqlalchemy import select
from test_corridas import crear, vaciar_cola, web  # noqa: F401
from test_descarga import ETAPAS, almacen  # noqa: F401
from test_fichar import ia_falsa, perfil, sitio  # noqa: F401

from docubot.db.modelos import Candidato, Corrida, Tarea
from docubot.eventos import CANAL, Difusor, publicar
from docubot.main import app
from docubot.pipeline import corridas


@pytest.fixture
async def api():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as cliente:
        yield cliente


@pytest.fixture
async def con_datos(tmp_path, sesiones, web, almacen, ia_falsa):
    """Una corrida completa: 2 documentos (uno con texto y uno escaneado) con sus fichas."""
    sitio(web)
    cargado = perfil(tmp_path)
    cid = await crear(sesiones, cargado, descargar=True)
    await vaciar_cola(sesiones, ETAPAS)
    return cid


async def test_biblioteca_filtros_y_detalle(con_datos, api):
    r = (await api.get("/api/documentos")).json()
    assert r["total"] == 2 and len(r["elementos"]) == 2
    por_estado = {d["ficha"]["estado"]: d for d in r["elementos"]}
    plan = por_estado["ok"]
    assert plan["titulo"] == "PLAN MUNICIPAL DE DESARROLLO 2024-2027" and plan["tipo"] == "PLAN"

    assert (await api.get("/api/documentos", params={"ficha": "revision"})).json()["total"] == 1
    assert (await api.get("/api/documentos", params={"q": "municipal de desarrollo"})).json()["total"] == 1
    assert (await api.get("/api/documentos", params={"perfil": "otro"})).json()["total"] == 0
    assert (await api.get("/api/documentos", params={"limite": 1})).json()["total"] == 2

    d = (await api.get(f"/api/documentos/{plan['id']}")).json()
    assert d["perfiles"] == ["fichas"] and d["texto"]["metodo"] == "texto"
    assert d["fichas"][0]["campos"]["fecha_publicacion"] == "2024-03-05"
    assert d["fuentes"][0]["url"].endswith("/plan-actopan.pdf")

    portada = await api.get(f"/api/documentos/{plan['id']}/portada")
    assert portada.status_code == 200 and portada.content[:3] == b"\xff\xd8\xff"
    archivo = await api.get(f"/api/documentos/{plan['id']}/archivo")
    assert archivo.content.startswith(b"%PDF")


async def test_revision_editar_aprobar_y_rehacer(con_datos, api, sesiones):
    cola_revision = (await api.get("/api/fichas")).json()
    assert cola_revision["total"] == 1
    pendiente = cola_revision["elementos"][0]
    assert pendiente["tipo_ia"] == "OTRO" and pendiente["tipo_esperado"] == "PLAN"
    doc = pendiente["documento_id"]

    r = await api.put(
        f"/api/documentos/{doc}/fichas/fichas",
        json={"campos": {"titulo": "Atlas de riesgos", "fecha_publicacion": "2020", "tema": "Riesgo"}},
    )
    assert r.status_code == 200 and r.json()["estado"] == "ok"
    d = (await api.get(f"/api/documentos/{doc}")).json()["fichas"][0]
    assert d["confianza"] == "manual" and d["campos"]["tema"] == "Riesgo" and d["control"]["editada"]
    assert (await api.get("/api/fichas")).json()["total"] == 0

    # sin título (requerido) queda en revisión; aprobar la saca
    r = await api.put(f"/api/documentos/{doc}/fichas/fichas", json={"campos": {"titulo": ""}})
    assert r.json()["estado"] == "revision" and "falta titulo" in r.json()["motivos"]
    assert (await api.post(f"/api/documentos/{doc}/fichas/fichas/aprobar")).json() == {"estado": "ok"}

    assert (await api.post(f"/api/documentos/{doc}/fichas/fichas/rehacer")).json() == {"encolada": True}
    async with sesiones() as s:
        assert await s.scalar(select(Tarea).where(Tarea.etapa == "fichar", Tarea.estado == "pendiente"))


async def test_candidatos_a_mano(tmp_path, sesiones, web, almacen, api):
    sitio(web)
    web.rutas["https://m.gob.mx/"] = web.rutas["https://m.gob.mx/"].__class__(
        200,
        headers={"Content-Type": "text/html"},
        text='<a href="/plan-actopan.pdf">Plan</a> <a href="/boletin.pdf">Boletin</a>',
    )
    cid = await crear(sesiones, perfil(tmp_path), descargar=False)
    await vaciar_cola(sesiones, ETAPAS)
    r = (await api.get("/api/candidatos", params={"corrida": cid})).json()
    assert r["total"] == 2
    rechazado = next(c for c in r["elementos"] if c["estado"] == "rechazado")
    assert (await api.get("/api/candidatos", params={"q": "boletin"})).json()["total"] == 1

    cambio = (await api.patch(f"/api/candidatos/{rechazado['id']}", json={"estado": "aceptado"})).json()
    assert cambio["estado"] == "aceptado" and cambio["motivo"] == "a mano" and cambio["descarga_encolada"]
    async with sesiones() as s:
        assert (await s.get(Corrida, cid)).estado == "corriendo"
    assert (await api.patch(f"/api/candidatos/{rechazado['id']}", json={"estado": "borrado"})).status_code == 422


async def test_corrida_con_ajustes_propios(tmp_path, sesiones, api, monkeypatch):
    from docubot.ajustes import obtener_ajustes

    archivo = tmp_path / "fichas.yaml"
    perfil(tmp_path)  # escribe el YAML
    monkeypatch.setenv("DOCUBOT_CARPETA_PERFILES", str(tmp_path))
    obtener_ajustes.cache_clear()
    try:
        r = await api.post(
            "/api/corridas",
            json={
                "perfil": "fichas",
                "descargar": False,
                "ajustes": {"respetar_robots": False, "profundidad": 4, "max_paginas": 9},
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["cambios"] == {"respetar_robots": False, "profundidad": 4, "max_paginas": 9}
        async with sesiones() as s:
            corrida = await s.get(Corrida, r.json()["id"])
            p = corridas.perfil_de(corrida)
        assert p.red.respetar_robots is False and p.descubrimiento.exploracion.profundidad == 4
        malo = await api.post("/api/corridas", json={"perfil": "fichas", "ajustes": {"profundidad": 99}})
        assert malo.status_code == 422
        assert (await api.get(f"/api/corridas/{r.json()['id']}/fallas")).json() == []
        assert "nombre: fichas" in (await api.get("/api/perfiles/fichas/yaml")).text
        assert archivo.exists()
    finally:
        obtener_ajustes.cache_clear()


async def test_resumen(con_datos, api):
    r = (await api.get("/api/resumen")).json()
    assert r["documentos"] == 2 and r["fichas"] == {"ok": 1, "revision": 1} and r["corridas_activas"] == 0


async def test_eventos_llegan_por_listen(sesiones):
    url = URL_PRUEBAS.replace("postgresql+psycopg://", "postgresql://")
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as escucha:
        await escucha.execute(f"LISTEN {CANAL}")
        async with sesiones() as s:
            await publicar(s, "ficha", documento_id=7, estado="ok", titulo="Plan")
            await s.commit()
        aviso = await asyncio.wait_for(anext(escucha.notifies()), 5)
    assert json.loads(aviso.payload) == {"tipo": "ficha", "documento_id": 7, "estado": "ok", "titulo": "Plan"}

    d = Difusor()
    lento, rapido = d.suscribir(), d.suscribir()
    for i in range(600):
        d.repartir(str(i))
    assert lento.qsize() == 500 and lento.get_nowait() == "100"  # pierde lo más viejo, no se bloquea
    d.cancelar(rapido)
    d.repartir("x")
    assert rapido.qsize() == 500
