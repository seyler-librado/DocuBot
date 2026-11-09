"""Evaluación de la IA contra un conjunto dorado."""

import json

from simulado import pdf_con_texto

from docubot.ajustes import AjustesIA
from docubot.ia.base import Proveedor, Respuesta
from docubot.ia.evaluar import comparar, evaluar
from docubot.perfiles.esquema import Campo, Perfil

PERFIL = Perfil.model_validate(
    {
        "nombre": "eval",
        "descubrimiento": {"fuentes": [{"tipo": "semillas", "urls": ["https://m.gob.mx/"]}]},
        "documentos": {"tipos": {"PMD": {"nombre": "Plan municipal de desarrollo", "palabras": ["plan"]}}},
        "fichas": {
            "campos": {
                "titulo": {"tipo": "texto", "requerido": True},
                "fecha_publicacion": {"tipo": "fecha"},
                "instancias": {"tipo": "lista"},
            }
        },
    }
)


class IAFija(Proveedor):
    nombre = "fija"

    def __init__(self, respuestas):
        super().__init__(AjustesIA(modelo="fija"))
        self.respuestas = respuestas

    async def _completar(self, sistema, usuario, imagenes):
        return Respuesta(json.dumps(self.respuestas.pop(0), ensure_ascii=False))


def test_comparar_por_tipo():
    texto, fecha, lista = Campo(tipo="texto"), Campo(tipo="fecha"), Campo(tipo="lista")
    assert comparar(texto, "Plan Municipal de Desarrollo 2024", "PLAN MUNICIPAL DE DESARROLLO 2024")
    assert not comparar(texto, "Plan Municipal de Desarrollo", "Atlas de riesgos")
    assert comparar(fecha, "05/03/2024", "2024-03-05")
    assert comparar(lista, "Ayuntamiento|IMPLAN", ["IMPLAN", "Ayuntamiento", "Cabildo"])
    assert not comparar(lista, "Ayuntamiento|IMPLAN", ["Gobierno del estado"])
    assert comparar(texto, "", None) and not comparar(texto, "", "algo")


async def test_evaluar(tmp_path):
    texto = (
        "PLAN MUNICIPAL DE DESARROLLO DE TULA 2024-2027\nH. Ayuntamiento de Tula\n" + "Objetivos del municipio. " * 10
    )
    (tmp_path / "a.pdf").write_bytes(pdf_con_texto([texto]))
    (tmp_path / "b.pdf").write_bytes(pdf_con_texto([texto]))
    (tmp_path / "dorado.csv").write_text(
        "archivo,titulo,fecha_publicacion,instancias,tipo_documento\n"
        "a.pdf,Plan Municipal de Desarrollo de Tula 2024-2027,2024-03-05,H. Ayuntamiento de Tula,PMD\n"
        "b.pdf,Plan Municipal de Desarrollo de Tula 2024-2027,2024-03-05,H. Ayuntamiento de Tula,PMD\n",
        encoding="utf-8",
    )
    ia = IAFija(
        [
            {
                "titulo": "PLAN MUNICIPAL DE DESARROLLO DE TULA 2024-2027",
                "fecha_publicacion": "5 de marzo de 2024",
                "instancias": ["H. Ayuntamiento de Tula"],
                "tipo_documento": "Plan municipal de desarrollo",
            },
            {"titulo": "Informe de gobierno", "fecha_publicacion": "2023", "instancias": [], "tipo_documento": "Otro"},
        ]
    )
    informe = await evaluar(PERFIL, tmp_path, ia, AjustesIA())
    por_campo = informe.por_campo()
    assert por_campo["titulo"] == {"aciertos": 1, "total": 2, "porcentaje": 50.0}
    assert por_campo["tipo_documento"]["aciertos"] == 1
    assert informe.global_ == 50.0
    assert informe.a_dict()["documentos"][0]["metodo"] == "texto"
