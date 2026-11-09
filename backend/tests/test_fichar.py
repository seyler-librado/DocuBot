"""De punta a punta: descubrir → descargar → extraer → ficha, con una IA de prueba."""

import json
import textwrap

import httpx
import pytest
from simulado import html, pdf_con_texto
from sqlalchemy import select
from test_corridas import crear, vaciar_cola, web  # noqa: F401
from test_descarga import ETAPAS, almacen  # noqa: F401

from docubot import ia
from docubot.ajustes import AjustesIA
from docubot.db.modelos import Corrida, Documento, Ficha, Tarea, Texto
from docubot.ia.base import Desborde, Proveedor, Respuesta
from docubot.perfiles import cargar
from docubot.pipeline import corridas

M = "https://m.gob.mx"
PLAN = (
    "PLAN MUNICIPAL DE DESARROLLO 2024-2027\nH. Ayuntamiento de Actopan\nPublicado el 5 de marzo de 2024\n"
    + "Diagnostico, objetivos y estrategias del municipio. " * 6
)


class IAFalsa(Proveedor):
    nombre = "falsa"
    vision = True

    def __init__(self, desbordes: int = 0):
        super().__init__(AjustesIA(modelo="falsa-1"))
        self.llamadas: list[dict] = []
        self.desbordes = desbordes

    async def _completar(self, sistema, usuario, imagenes):
        self.llamadas.append({"sistema": sistema, "usuario": usuario, "imagenes": len(imagenes)})
        if self.desbordes:
            self.desbordes -= 1
            raise Desborde("no cabe")
        if imagenes:
            ficha = {"titulo": "Atlas de riesgos", "tipo_documento": "Otro"}
        else:
            ficha = {
                "titulo": "PLAN MUCIPAL DE DESARROLLO 2024-2027",
                "fecha_publicacion": "05/03/2024",
                "tema": "desarrollo urbano",
                "tipo_documento": "Plan",
            }
        return Respuesta(f"Aquí está:\n```json\n{json.dumps(ficha, ensure_ascii=False)}\n```", "falsa-1", 100, 20)


@pytest.fixture
def ia_falsa():
    falsa = IAFalsa()
    ia.usar_proveedor(falsa)
    yield falsa
    ia.usar_proveedor(None)


def perfil(tmp_path):
    archivo = tmp_path / "fichas.yaml"
    archivo.write_text(
        textwrap.dedent(f"""
        nombre: fichas
        descubrimiento:
          fuentes:
            - tipo: semillas
              urls: [{M}/]
          exploracion: {{sitemap: false, profundidad: 1}}
        documentos:
          tipos:
            PLAN: {{nombre: Plan, palabras: [plan]}}
        fichas:
          campos:
            titulo: {{tipo: texto, requerido: true}}
            fecha_publicacion: {{tipo: fecha}}
            tema: {{tipo: opcion, opciones: [Desarrollo urbano, Riesgo]}}
        red:
          peticiones_por_segundo_por_dominio: 1000
    """),
        encoding="utf-8",
    )
    c = cargar(archivo)
    assert c.valido, c.errores
    return c


def sitio(web):
    web.rutas |= {
        f"{M}/": html(("/plan-actopan.pdf", "Plan municipal"), ("/plan-escaneado.pdf", "Plan escaneado")),
        f"{M}/plan-actopan.pdf": httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=pdf_con_texto([PLAN])
        ),
        f"{M}/plan-escaneado.pdf": httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=pdf_con_texto(["", ""])
        ),
    }


async def fichas_por_metodo(sesiones) -> dict[str, Ficha]:
    async with sesiones() as s:
        return {f.control.get("metodo"): f for f in await s.scalars(select(Ficha))}


async def test_pipeline_completo(tmp_path, sesiones, web, almacen, ia_falsa):
    sitio(web)
    cid = await crear(sesiones, perfil(tmp_path), descargar=True)
    await vaciar_cola(sesiones, ETAPAS)

    async with sesiones() as s:
        textos = {t.metodo: t for t in await s.scalars(select(Texto))}
        corrida = await s.get(Corrida, cid)
        r = await corridas.resumen(s, corrida)
        documentos = (await s.scalars(select(Documento))).all()
    assert set(textos) == {"texto", "escaneado"}
    assert "PLAN MUNICIPAL DE DESARROLLO" in textos["texto"].contenido
    assert {d.estado for d in documentos} == {"texto", "escaneado"}
    assert corrida.estado == "terminada" and r["fichas"] == {"ok": 1, "revision": 1}

    f = await fichas_por_metodo(sesiones)
    plan = f["texto"]
    assert plan.estado == "ok" and plan.confianza == "alta"
    assert plan.campos == {
        "titulo": "PLAN MUNICIPAL DE DESARROLLO 2024-2027",  # errata corregida contra el texto
        "fecha_publicacion": "2024-03-05",
        "tema": "Desarrollo urbano",
    }
    assert plan.modelo == "falsa-1" and plan.control["tipo_ia"] == "PLAN"

    escaneado = f["imagen"]
    assert escaneado.estado == "revision" and escaneado.confianza == "baja"
    assert "la IA dice que es otro tipo de documento" in escaneado.motivos
    assert escaneado.control["imagenes"] == 2

    # a la IA no se le dice qué tipo se espera, y recibe el texto del documento
    con_texto = next(x for x in ia_falsa.llamadas if not x["imagenes"])
    assert "PLAN MUNICIPAL DE DESARROLLO" in con_texto["usuario"]
    assert "PLAN" not in con_texto["sistema"].split("Llaves:")[0]


async def test_si_no_cabe_se_recorta(tmp_path, sesiones, web, almacen):
    falsa = IAFalsa(desbordes=2)
    ia.usar_proveedor(falsa)
    try:
        sitio(web)
        web.rutas[f"{M}/"] = html(("/plan-actopan.pdf", "Plan municipal"))
        await crear(sesiones, perfil(tmp_path), descargar=True)
        await vaciar_cola(sesiones, ETAPAS)
    finally:
        ia.usar_proveedor(None)
    largos = [len(x["usuario"]) for x in falsa.llamadas]
    assert len(largos) == 3 and largos[0] > largos[1] > largos[2]
    f = await fichas_por_metodo(sesiones)
    assert f["texto"].estado == "ok"


async def test_sin_ia_no_hay_fichas(tmp_path, sesiones, web, almacen):
    sitio(web)
    cid = await crear(sesiones, perfil(tmp_path), descargar=True)
    await vaciar_cola(sesiones, ETAPAS)
    async with sesiones() as s:
        etapas = set(await s.scalars(select(Tarea.etapa).where(Tarea.corrida_id == cid)))
        corrida = await s.get(Corrida, cid)
    assert "extraer" in etapas and "fichar" not in etapas
    assert corrida.estado == "terminada"
