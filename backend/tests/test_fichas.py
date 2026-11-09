from docubot.ia import fichas as F
from docubot.perfiles.esquema import Perfil


def perfil() -> Perfil:
    datos = {
        "nombre": "fichas",
        "descubrimiento": {"fuentes": [{"tipo": "semillas", "urls": ["https://m.gob.mx/"]}]},
        "documentos": {"tipos": {"PMD": {"nombre": "Plan municipal de desarrollo", "palabras": ["plan"]}}},
        "fichas": {
            "campos": {
                "titulo": {"tipo": "texto", "requerido": True, "descripcion": "título oficial"},
                "fecha_publicacion": {"tipo": "fecha"},
                "tema": {"tipo": "opcion", "opciones": ["Desarrollo urbano", "Riesgo", "Movilidad"]},
                "instancias": {"tipo": "lista"},
                "temas": {"tipo": "lista", "opciones": ["Agua", "Vivienda"]},
                "habitantes": {"tipo": "numero"},
            },
            "instrucciones": "Son documentos de gobiernos municipales.",
        },
    }
    return Perfil.model_validate(datos)


def test_instrucciones_salen_del_perfil():
    texto = F.instrucciones(perfil())
    assert '- "titulo": título oficial. (importante)' in texto
    assert "Uno de: Desarrollo urbano | Riesgo | Movilidad." in texto
    assert '"tipo_documento": qué es el documento, uno de: Plan municipal de desarrollo | Otro.' in texto
    assert "Son documentos de gobiernos municipales." in texto
    assert texto.endswith("Responde únicamente con un bloque ```json con esas llaves.")


def test_json_laxo():
    assert F.json_laxo('Claro:\n```json\n{"a": 1,}\n```\nListo') == {"a": 1}
    assert F.json_laxo('La ficha es {"a": "x {y}", "b": [1, 2,]} y nada más') == {"a": "x {y}", "b": [1, 2]}
    assert F.json_laxo("{“a”: “b”}") == {"a": "b"}
    assert F.json_laxo("no hay json") is None
    assert F.json_laxo("") is None


def test_fechas():
    assert F.fecha("2024-3-5") == "2024-03-05"
    assert F.fecha("05/03/2024") == "2024-03-05"
    assert F.fecha("5 de marzo de 2024") == "2024-03-05"
    assert F.fecha("marzo de 2024") == "2024-03"
    assert F.fecha("2024") == "2024"
    assert F.fecha("sin fecha") is None


def test_validar_corrige_y_normaliza():
    texto = "PLAN MUNICIPAL DE DESARROLLO DE ACTOPAN\nH. Ayuntamiento de Actopan\nInstituto Municipal de Planeación"
    datos = {
        "titulo": "PLAN MUCIPAL DE DESARULLO DE ACTOPAN",
        "fecha_publicacion": "15/01/2025",
        "tema": "desarrollo URBANO",
        "instancias": "H. Ayuntamiento de Actopan; Instituto Municipal de Planeacion",
        "temas": ["agua", "Educación"],
        "habitantes": "57,000 habitantes",
        "tipo_documento": "Plan Municipal de Desarrollo",
    }
    v = F.validar(datos, perfil(), texto)
    assert v.campos["titulo"] == "PLAN MUNICIPAL DE DESARROLLO DE ACTOPAN"
    assert v.campos["fecha_publicacion"] == "2025-01-15"
    assert v.campos["tema"] == "Desarrollo urbano"
    assert v.campos["instancias"] == ["H. Ayuntamiento de Actopan", "Instituto Municipal de Planeación"]
    assert v.campos["temas"] == ["Agua"]
    assert v.campos["habitantes"] == 57000
    assert v.tipo_ia == "PMD"
    assert v.motivos == []


def test_validar_reporta_lo_que_no_cuadra():
    v = F.validar({"tema": "Turismo", "fecha_publicacion": "ayer", "tipo_documento": "Otro"}, perfil(), "")
    assert v.campos["titulo"] is None and v.campos["tema"] is None
    assert "falta titulo" in v.motivos
    assert any("no es una de las opciones" in m for m in v.motivos)
    assert any("fecha no reconocida" in m for m in v.motivos)
    assert v.tipo_ia == "OTRO"


def test_contaminada_y_calificar():
    p = perfil()
    assert F.contaminada({"titulo": "Reglamento de tránsito"}, p, "Plan municipal de desarrollo") == (
        "el título no aparece en el texto del documento"
    )
    assert F.contaminada({"titulo": "Plan municipal"}, p, "PLAN MUNICIPAL DE DESARROLLO") is None

    assert F.calificar([], "texto", "PMD", "PMD") == ("ok", "alta", [])
    assert F.calificar([], "imagen", "PMD", "PMD") == ("ok", "media", [])
    estado, confianza, motivos = F.calificar([], "texto", "OTRO", "PMD")
    assert (estado, confianza) == ("revision", "baja")
    assert motivos == ["la IA dice que es otro tipo de documento"]
    assert F.calificar(["temas: algo"], "texto", None, None)[:2] == ("ok", "media")
