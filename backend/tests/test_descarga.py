"""Calificar, descargar y guardar por huella, con la web simulada."""

import textwrap

import httpx
import pytest
from simulado import html
from sqlalchemy import select, text
from test_corridas import crear, vaciar_cola, web  # noqa: F401  (web es un fixture)

from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Corrida, Documento
from docubot.perfiles import cargar
from docubot.pipeline import corridas, descargas
from docubot.pipeline.recalificar import recalificar

M = "https://m.gob.mx"
PDF = b"%PDF-1.4\ncontenido de prueba\n%%EOF\n"
PDF_ARCHIVO = b"%PDF-1.4\ncopia del Internet Archive\n%%EOF\n"


def respuesta_pdf(contenido: bytes) -> httpx.Response:
    return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=contenido)


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    carpeta = tmp_path / "almacen"
    monkeypatch.setenv("DOCUBOT_ALMACEN__CARPETA", str(carpeta))
    obtener_ajustes.cache_clear()
    yield carpeta
    obtener_ajustes.cache_clear()


def perfil(tmp_path, extra: str = ""):
    archivo = tmp_path / "descarga.yaml"
    archivo.write_text(
        textwrap.dedent(
            f"""
            nombre: descarga
            descubrimiento:
              fuentes:
                - tipo: semillas
                  urls: [{M}/]
              exploracion: {{sitemap: false, profundidad: 1}}
            documentos:
              tipos:
                PLAN: {{nombre: Plan, palabras: [plan]}}
              excluir: [formato]
              tamano_max_mb: 1
            red:
              peticiones_por_segundo_por_dominio: 1000
            """
        )
        + extra,
        encoding="utf-8",
    )
    c = cargar(archivo)
    assert c.valido, c.errores
    return c


def sitio(web):
    web.rutas |= {
        f"{M}/": html(
            ("/plan-bueno.pdf", "Plan municipal"),
            ("/plan-copia.pdf", "Plan (copia)"),
            ("/plan-html.pdf", "Plan"),
            ("/plan-cortado.pdf", "Plan"),
            ("/plan-grande.pdf", "Plan"),
            ("/plan-404.pdf", "Plan"),
            ("/plan-caido.pdf", "Plan"),
            ("/formato-plan.pdf", "Formato de solicitud"),
            ("/boletin.pdf", "Boletín"),
        ),
        f"{M}/plan-bueno.pdf": respuesta_pdf(PDF),
        f"{M}/plan-copia.pdf": respuesta_pdf(PDF),
        f"{M}/plan-html.pdf": html(),
        f"https://web.archive.org/web/2id_/{M}/plan-html.pdf": respuesta_pdf(PDF_ARCHIVO),
        f"{M}/plan-cortado.pdf": respuesta_pdf(b"%PDF-1.4 se corta aqu"),
        f"{M}/plan-grande.pdf": respuesta_pdf(b"%PDF-1.4" + b"x" * (2 * 1024 * 1024)),
        f"{M}/plan-caido.pdf": httpx.Response(503),
    }


async def vencer_esperas(sesiones) -> None:
    async with sesiones() as s:
        await s.execute(text("UPDATE tareas SET disponible_en = now() WHERE estado = 'pendiente'"))
        await s.commit()


async def por_url(sesiones) -> dict[str, Candidato]:
    async with sesiones() as s:
        return {c.url.removeprefix(M): c for c in await s.scalars(select(Candidato))}


ETAPAS = ("descubrir", "explorar", "descargar", "extraer", "fichar")


async def test_califica_descarga_y_guarda_por_huella(tmp_path, sesiones, web, almacen):
    sitio(web)
    cid = await crear(sesiones, perfil(tmp_path), descargar=True)
    await vaciar_cola(sesiones, ETAPAS)
    for _ in range(3):  # el sitio caído agota sus reintentos
        await vencer_esperas(sesiones)
        await vaciar_cola(sesiones, ETAPAS)

    c = await por_url(sesiones)
    estados = {u: x.estado for u, x in c.items()}
    assert estados == {
        "/plan-bueno.pdf": "descargado",
        "/plan-copia.pdf": "descargado",
        "/plan-html.pdf": "descargado",
        "/plan-cortado.pdf": "fallido",
        "/plan-grande.pdf": "fallido",
        "/plan-404.pdf": "fallido",
        "/plan-caido.pdf": "fallido",
        "/formato-plan.pdf": "rechazado",
        "/boletin.pdf": "rechazado",
    }
    assert c["/plan-cortado.pdf"].motivo == "el PDF está incompleto (no termina en %%EOF)"
    assert c["/plan-grande.pdf"].motivo == "pesa más de 1 MB"
    assert c["/plan-404.pdf"].motivo == "el sitio respondió 404"
    assert c["/plan-caido.pdf"].motivo == "el sitio respondió 503"
    assert c["/formato-plan.pdf"].motivo == "excluido por «formato»"
    assert c["/plan-bueno.pdf"].puntaje == 85

    # mismo contenido en dos URLs: un solo documento
    assert c["/plan-bueno.pdf"].documento_id == c["/plan-copia.pdf"].documento_id
    assert c["/plan-html.pdf"].datos["respaldo"] == "wayback"

    async with sesiones() as s:
        documentos = (await s.scalars(select(Documento))).all()
        corrida = await s.get(Corrida, cid)
        r = await corridas.resumen(s, corrida)
    assert len(documentos) == 2
    contenidos = {(almacen / d.ruta).read_bytes() for d in documentos}
    assert contenidos == {PDF, PDF_ARCHIVO}
    assert list((almacen / ".tmp").iterdir()) == []
    assert corrida.estado == "terminada"
    assert r["documentos"] == 2 and r["candidatos_estado"]["descargado"] == 3
    # el 503 se pidió una vez por intento de la tarea (más los reintentos del cliente)
    assert len(web.pedidas(f"{M}/plan-caido.pdf")) >= 3


async def test_corrida_sin_descarga_y_descarga_posterior(tmp_path, sesiones, web, almacen):
    sitio(web)
    cid = await crear(sesiones, perfil(tmp_path), descargar=False)
    await vaciar_cola(sesiones, ETAPAS)
    assert not web.pedidas(f"{M}/plan-bueno.pdf")
    async with sesiones() as s:
        assert (await s.get(Corrida, cid)).estado == "terminada"
        n = await descargas.descargar_corrida(s, cid, limite=2)
        await s.commit()
    assert n == 2
    await vaciar_cola(sesiones, ETAPAS)
    c = await por_url(sesiones)
    assert sum(x.estado == "descargado" for x in c.values()) == 2


async def test_referencia_marca_lo_nuevo(tmp_path, sesiones, web, almacen):
    sitio(web)
    (tmp_path / "ya.csv").write_text(f"url\n{M}/plan-bueno.pdf\n", encoding="utf-8")
    cargado = perfil(tmp_path, "referencia: {archivo: ya.csv, llave: [url]}\n")
    await crear(sesiones, cargado, descargar=False)
    await vaciar_cola(sesiones, ETAPAS)
    c = await por_url(sesiones)
    assert c["/plan-bueno.pdf"].datos["nuevo"] is False
    assert c["/plan-copia.pdf"].datos["nuevo"] is True


async def test_recalificar(tmp_path, sesiones, web, almacen):
    sitio(web)
    cargado = perfil(tmp_path)
    await crear(sesiones, cargado, descargar=False)
    await vaciar_cola(sesiones, ETAPAS)
    otro = cargado.perfil.model_copy(deep=True)
    otro.documentos.excluir = []
    otro.documentos.tipos["BOLETIN"] = otro.documentos.tipos["PLAN"].model_copy(update={"palabras": ["boletin"]})
    async with sesiones() as s:
        perfil_id = (await s.scalar(select(Candidato))).perfil_id
        cuenta = await recalificar(s, perfil_id, otro)
        await s.commit()
    assert cuenta["cambiados"] == 2  # formato-plan y boletin ahora se aceptan
    c = await por_url(sesiones)
    assert c["/boletin.pdf"].estado == "aceptado" and c["/boletin.pdf"].tipo == "BOLETIN"
