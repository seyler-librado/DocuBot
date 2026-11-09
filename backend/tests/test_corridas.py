"""Corridas de punta a punta: perfil → tareas → fuentes/exploración → candidatos, con la web simulada."""

import json
import textwrap

import httpx
import pytest
from simulado import Servidor, html, pdf
from sqlalchemy import func, select

from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Corrida, CorridaSitio, Sitio, Tarea
from docubot.perfiles import cargar
from docubot.pipeline import cola, corridas
from docubot.pipeline.etapas import ETAPAS
from docubot.pipeline.trabajador import procesar_una
from docubot.red import clientes


@pytest.fixture
def web():
    """Instala un servidor simulado para todos los clientes HTTP de DocuBot."""
    servidor = Servidor({})
    clientes.usar_transporte(httpx.MockTransport(servidor), espera_base=0.01, ritmo_api=1000)
    yield servidor
    clientes.usar_transporte(None)


def perfil(tmp_path, fuentes: str, extra: str = ""):
    texto = textwrap.dedent(
        """
        nombre: prueba
        descubrimiento:
          dominios:
            permitir: ["*.gob.mx"]
          fuentes:
        {fuentes}
          exploracion: {{sitemap: false, profundidad: 1}}
        documentos:
          tipos:
            PLAN: {{nombre: Plan, palabras: [plan]}}
        red:
          peticiones_por_segundo_por_dominio: 1000
        {extra}
        """
    ).format(fuentes=textwrap.indent(textwrap.dedent(fuentes).strip(), "    "), extra=extra)
    archivo = tmp_path / "prueba.yaml"
    archivo.write_text(texto, encoding="utf-8")
    c = cargar(archivo)
    assert c.valido, c.errores
    return c


async def vaciar_cola(sesiones, etapas=("descubrir", "explorar"), maximo=500) -> None:
    for _ in range(maximo):
        hubo = False
        for nombre in etapas:
            async with sesiones() as s:
                tareas = await cola.tomar(s, nombre, "prueba")
                await s.commit()
            if tareas:
                await procesar_una(ETAPAS[nombre], tareas[0], sesiones)
                hubo = True
        if not hubo:
            return
    raise AssertionError("la cola no se vació")


async def crear(sesiones, cargado, fuentes=None, descargar=False) -> int:
    async with sesiones() as s:
        c = await corridas.crear(s, cargado, fuentes, descargar=descargar)
        await s.commit()
        return c.id


async def candidatos(sesiones) -> dict[str, Candidato]:
    async with sesiones() as s:
        return {c.url: c for c in await s.scalars(select(Candidato))}


async def test_semillas_y_exploracion(tmp_path, sesiones, web):
    web.rutas |= {
        "https://m.gob.mx/": html(("/plan.pdf", "Plan municipal"), ("/docs", "Documentos")),
        "https://m.gob.mx/docs": html(("/plan.pdf", "Plan (otra vez)"), ("/plan-2.pdf", "Plan 2")),
    }
    cargado = perfil(
        tmp_path,
        """
        - tipo: semillas
          urls: [https://m.gob.mx/, https://m.gob.mx/suelto.pdf, https://otro.com/]
    """,
    )
    cid = await crear(sesiones, cargado)
    await vaciar_cola(sesiones)

    docs = await candidatos(sesiones)
    assert set(docs) == {"https://m.gob.mx/plan.pdf", "https://m.gob.mx/plan-2.pdf", "https://m.gob.mx/suelto.pdf"}
    assert docs["https://m.gob.mx/plan.pdf"].ancla == "Plan municipal"
    assert docs["https://m.gob.mx/plan.pdf"].tipo == "PLAN"
    assert docs["https://m.gob.mx/plan.pdf"].fuente == "crawler"
    assert docs["https://m.gob.mx/suelto.pdf"].fuente == "semillas"

    async with sesiones() as s:
        corrida = await s.get(Corrida, cid)
        assert corrida.estado == "terminada" and corrida.error is None
        r = await corridas.resumen(s, corrida)
        assert r["sitios"] == {"explorado": 1}  # otro.com no está permitido
        assert r["paginas"] == 2 and r["candidatos_total"] == 3
        sitio = await s.scalar(select(Sitio))
        assert sitio.dominio == "m.gob.mx" and sitio.estado == "explorado"


async def test_buscador_con_variables_reparte_consultas(tmp_path, sesiones, web):
    (tmp_path / "municipios.csv").write_text("clave,municipio\n13001,Acatlán\n13002,Actopan\n", encoding="utf-8")
    (tmp_path / "lugares.csv").write_text(
        "clave,nombre,nivel\n13001,Acatlán,municipio\n13002,Actopan,municipio\n", encoding="utf-8"
    )
    respuestas = {
        "plan Acatlán": [
            {"url": "https://acatlan.gob.mx/transparencia", "title": "Transparencia"},
            {"url": "https://acatlan.gob.mx/plan.pdf", "title": "Plan municipal de Acatlán"},
            {"url": "https://www.facebook.com/acatlan", "title": "Facebook"},
            {"url": "https://noticias.com/acatlan", "title": "Noticia"},
        ],
        "plan Actopan": [
            {"url": "https://actopan.gob.mx/", "title": "Inicio"},
            {"url": "https://acatlan.gob.mx/otra", "title": "Acatlán otra página"},
        ],
    }

    def searxng(peticion):
        consulta = peticion.url.params["q"]
        pagina = int(peticion.url.params["pageno"])
        resultados = respuestas.get(consulta, []) if pagina == 1 else []
        return httpx.Response(200, json={"results": resultados})

    web.rutas["http://searxng:8080/search"] = searxng
    cargado = perfil(
        tmp_path,
        """
        - tipo: buscador
          motor: searxng
          consultas: ['plan {municipio}']
          variables: municipios.csv
          columna_lugar: clave
        """,
        extra="geografia: {catalogo: lugares.csv}",
    )
    cid = await crear(sesiones, cargado)
    await vaciar_cola(sesiones, etapas=("descubrir",))  # solo descubrir: no explorar todavía

    async with sesiones() as s:
        partes = (await s.scalars(select(Tarea).where(Tarea.etapa == "descubrir"))).all()
        assert len(partes) == 3  # la tarea inicial + una por consulta
        filas = (
            await s.execute(
                select(Sitio.dominio, CorridaSitio.semillas, CorridaSitio.lugar)
                .join(CorridaSitio, CorridaSitio.sitio_id == Sitio.id)
                .where(CorridaSitio.corrida_id == cid)
                .order_by(Sitio.dominio)
            )
        ).all()
        explorar = await s.scalar(select(func.count()).where(Tarea.etapa == "explorar"))
    assert [f.dominio for f in filas] == ["acatlan.gob.mx", "actopan.gob.mx"]
    acatlan = filas[0]
    # el sitio se registró una vez, con las semillas de ambas consultas y el lugar de la primera
    assert sorted(acatlan.semillas) == ["https://acatlan.gob.mx/otra", "https://acatlan.gob.mx/transparencia"]
    assert acatlan.lugar == "13001" and filas[1].lugar == "13002"
    assert explorar == 2

    docs = await candidatos(sesiones)
    assert list(docs) == ["https://acatlan.gob.mx/plan.pdf"]
    assert docs["https://acatlan.gob.mx/plan.pdf"].datos["lugar"] == "13001"
    assert docs["https://acatlan.gob.mx/plan.pdf"].datos["consulta"] == "plan Acatlán"


async def test_lista_de_dominios(tmp_path, sesiones, web):
    (tmp_path / "sitios.csv").write_text(
        "dominio;clave\nhttps://www.uno.gob.mx/;1\ndos.gob.mx/docs/planes;2\n;3\nfuera.com;4\n", encoding="utf-8"
    )
    (tmp_path / "lugares.csv").write_text("clave,nombre,nivel\n1,Uno,m\n", encoding="utf-8")
    cargado = perfil(
        tmp_path,
        """
        - tipo: lista_dominios
          archivo: sitios.csv
          columna_lugar: clave
        """,
        extra="geografia: {catalogo: lugares.csv}",
    )
    cid = await crear(sesiones, cargado)
    await vaciar_cola(sesiones, etapas=("descubrir",))
    async with sesiones() as s:
        filas = {
            d: (sem, lugar)
            for d, sem, lugar in await s.execute(
                select(Sitio.dominio, CorridaSitio.semillas, CorridaSitio.lugar)
                .join(CorridaSitio, CorridaSitio.sitio_id == Sitio.id)
                .where(CorridaSitio.corrida_id == cid)
            )
        }
    assert filas == {"uno.gob.mx": ([], "1"), "dos.gob.mx": (["https://dos.gob.mx/docs/planes"], "2")}


async def test_commoncrawl_y_wayback(tmp_path, sesiones, web):
    cdx = "https://index.commoncrawl.org/CC-MAIN-2026-40-index"

    def cc(peticion):
        if peticion.url.params.get("showNumPages"):
            return httpx.Response(200, text='{"pages": 2, "pageSize": 5, "blocks": 9}')
        pagina = peticion.url.params["page"]
        filas = {
            "0": [{"url": "https://a.gob.mx/1.pdf", "timestamp": "20260901"}, {"url": "https://x.com/2.pdf"}],
            "1": [{"url": "https://b.gob.mx/3.pdf", "timestamp": "20260902"}, {"url": "https://a.gob.mx/1.pdf"}],
        }[pagina]
        return httpx.Response(200, text="\n".join(json.dumps(f) for f in filas))

    web.rutas |= {
        "https://index.commoncrawl.org/collinfo.json": httpx.Response(
            200, json=[{"id": "CC-MAIN-2026-40", "cdx-api": cdx}, {"id": "viejo", "cdx-api": "https://viejo"}]
        ),
        cdx: cc,
        "https://web.archive.org/cdx/search/cdx": httpx.Response(
            200,
            json=[["original", "mimetype", "timestamp"], ["https://c.gob.mx/4.pdf", "application/pdf", "20190101"]],
        ),
    }
    cargado = perfil(
        tmp_path,
        """
        - tipo: commoncrawl
          patron: "*.gob.mx"
        - tipo: wayback
          patron: "*.gob.mx"
    """,
    )
    await crear(sesiones, cargado)
    await vaciar_cola(sesiones)
    docs = await candidatos(sesiones)
    assert set(docs) == {"https://a.gob.mx/1.pdf", "https://b.gob.mx/3.pdf", "https://c.gob.mx/4.pdf"}
    assert docs["https://a.gob.mx/1.pdf"].fuente == "commoncrawl"
    assert docs["https://c.gob.mx/4.pdf"].datos == {"wayback": "20190101"}
    wb = [u for u in web.urls() if "web.archive.org" in u][0]
    assert "matchType=domain" in wb and "url=gob.mx" in wb


async def test_buscador_sin_llave_falla_de_inmediato(tmp_path, sesiones, web):
    obtener_ajustes.cache_clear()
    cargado = perfil(
        tmp_path,
        """
        - tipo: buscador
          motor: brave
          consultas: [plan]
    """,
    )
    cid = await crear(sesiones, cargado)
    await vaciar_cola(sesiones)
    async with sesiones() as s:
        tarea = await s.scalar(select(Tarea).where(Tarea.corrida_id == cid))
        corrida = await s.get(Corrida, cid)
    assert tarea.estado == "fallida" and tarea.intentos == 1
    assert "DOCUBOT_BUSCADORES__BRAVE_LLAVE" in tarea.error
    assert corrida.estado == "terminada" and corrida.error == "1 tarea(s) fallaron"


async def test_detener_y_reanudar(tmp_path, sesiones, web):
    (tmp_path / "sitios.csv").write_text("dominio\nuno.gob.mx\ndos.gob.mx\ntres.gob.mx\n", encoding="utf-8")
    cargado = perfil(
        tmp_path,
        """
        - tipo: lista_dominios
          archivo: sitios.csv
    """,
    )
    cid = await crear(sesiones, cargado)
    await vaciar_cola(sesiones, etapas=("descubrir",))
    async with sesiones() as s:
        assert await corridas.detener(s, cid) == 3
        await s.commit()
    await vaciar_cola(sesiones)  # no hay nada que tomar
    async with sesiones() as s:
        assert (await s.get(Corrida, cid)).estado == "detenida"
        assert await corridas.reanudar(s, cid) == 3
        await s.commit()
    await vaciar_cola(sesiones)
    async with sesiones() as s:
        corrida = await s.get(Corrida, cid)
        r = await corridas.resumen(s, corrida)
    assert corrida.estado == "terminada"
    assert r["sitios"] == {"sin_respuesta": 3}  # el servidor simulado no tiene esos sitios


async def test_dos_corridas_no_duplican_candidatos(tmp_path, sesiones, web):
    web.rutas["https://m.gob.mx/"] = html(("/plan.pdf", "Plan"))
    cargado = perfil(
        tmp_path,
        """
        - tipo: semillas
          urls: [https://m.gob.mx/]
    """,
    )
    primera = await crear(sesiones, cargado)
    await vaciar_cola(sesiones)
    segunda = await crear(sesiones, cargado)
    await vaciar_cola(sesiones)
    async with sesiones() as s:
        filas = (await s.scalars(select(Candidato))).all()
        sitios = await s.scalar(select(func.count()).select_from(Sitio))
    assert len(filas) == 1 and sitios == 1
    assert filas[0].corrida_id == segunda != primera  # la última corrida que lo vio


async def test_fuente_inexistente(tmp_path, sesiones):
    cargado = perfil(
        tmp_path,
        """
        - tipo: semillas
          urls: [https://m.gob.mx/]
    """,
    )
    async with sesiones() as s:
        with pytest.raises(corridas.ErrorCorrida, match="no existe"):
            await corridas.crear(s, cargado, [3])
