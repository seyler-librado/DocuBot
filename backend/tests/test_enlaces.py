from docubot.descubrimiento import enlaces as E
from docubot.descubrimiento.fuentes import _consulta_wayback
from docubot.descubrimiento.variables import consultas
from docubot.filtros.tipos import Clasificador, normalizar
from docubot.perfiles.esquema import Documentos, FuenteBuscador


def test_extrae_enlaces_con_su_texto():
    html = """
    <base href="https://m.gob.mx/docs/">
    <a href="plan.pdf">Plan Municipal</a>
    <a href="#arriba">arriba</a>
    <a href="mailto:x@m.gob.mx">correo</a>
    <a href="/atlas.pdf"><img src="i.png" alt="Atlas de riesgos"></a>
    <table><tr><td>Reglamento de tránsito 2023</td><td><a href="r.pdf">ver</a></td></tr></table>
    <iframe src="https://drive.google.com/file/d/XYZ/preview"></iframe>
    <a href="plan.pdf#page=2">otra vez</a>
    """
    enlaces = {e.url: e for e in E.extraer_enlaces(html, "https://m.gob.mx/")}
    assert set(enlaces) == {
        "https://m.gob.mx/docs/plan.pdf",
        "https://m.gob.mx/atlas.pdf",
        "https://m.gob.mx/docs/r.pdf",
        "https://drive.google.com/file/d/XYZ/preview",
    }
    assert enlaces["https://m.gob.mx/docs/plan.pdf"].ancla == "Plan Municipal"
    assert enlaces["https://m.gob.mx/atlas.pdf"].ancla == "Atlas de riesgos"
    assert enlaces["https://m.gob.mx/docs/r.pdf"].ancla == "Reglamento de tránsito 2023 ver"
    assert enlaces["https://drive.google.com/file/d/XYZ/preview"].etiqueta == "iframe"


def test_url_directa():
    assert E.url_directa("https://drive.google.com/file/d/AbC-1/view?usp=sharing") == (
        "https://drive.google.com/uc?export=download&id=AbC-1"
    )
    assert E.url_directa("https://drive.google.com/open?id=Q9") == "https://drive.google.com/uc?export=download&id=Q9"
    assert E.url_directa("https://docs.google.com/document/d/D1/edit") == (
        "https://docs.google.com/document/d/D1/export?format=pdf"
    )
    assert E.url_directa("https://www.dropbox.com/s/k/plan.pdf?dl=0") == "https://www.dropbox.com/s/k/plan.pdf?dl=1"
    assert E.url_directa("https://m.gob.mx/plan.pdf") == "https://m.gob.mx/plan.pdf"


def test_tipo_de_respuesta():
    mimes = E.mimes_de(["pdf"])
    assert E.tipo_de_respuesta("application/pdf; charset=binary", None, mimes, ["pdf"]) == "application/pdf"
    assert (
        E.tipo_de_respuesta("application/octet-stream", 'attachment; filename="Plan 2024.PDF"', mimes, ["pdf"])
        == "application/pdf"
    )
    assert (
        E.tipo_de_respuesta(
            "application/octet-stream", "attachment; filename*=UTF-8''Programa%20urbano.pdf", mimes, ["pdf"]
        )
        == "application/pdf"
    )
    assert E.tipo_de_respuesta("text/html", None, mimes, ["pdf"]) is None


def test_redes_visores_y_estacionados():
    assert E.es_red_social("https://www.facebook.com/municipio")
    assert E.es_red_social("m.facebook.com")
    assert not E.es_red_social("https://facebookmx.gob.mx/")
    assert E.es_visor("https://drive.google.com/file/d/1/view")
    assert E.estacionado("https://www.sedoparking.com/x")
    assert E.estacionado("https://m.gob.mx/", "<h1>This domain is for sale!</h1>")
    assert not E.estacionado("https://m.gob.mx/", "<h1>Bienvenidos</h1>")


def test_clasificador_normaliza_acentos_y_separadores():
    c = Clasificador(
        Documentos(
            tipos={
                "PMD": {"nombre": "Plan", "patrones": [r"plan\s*municipal\s*de\s*desarrollo"]},
                "PC": {"nombre": "Protección civil", "patrones": ["protección civil"]},
                "ATLAS": {"nombre": "Atlas", "palabras": ["atlas de riesgo"]},
            },
            excluir=["solicitud"],
        )
    )
    assert normalizar("PLAN_Municipal-de%20Desarrollo.pdf") == "plan municipal de desarrollo pdf"
    assert c.tipo_de("https://m.gob.mx/PLAN_Municipal-de%20Desarrollo_2024.pdf") == "PMD"
    assert c.tipo_de("Programa de PROTECCION CIVIL") == "PC"
    assert c.tipo_de(None, "Atlas de Riesgo municipal") == "ATLAS"
    assert c.tipo_de("atlasderiesgo") is None
    assert c.excluido("Solicitud de licencia")
    assert c.interesa("plan municipal de desarrollo") and not c.interesa("noticias")


def test_consultas_con_variables(tmp_path):
    (tmp_path / "m.csv").write_text(
        "clave;municipio;estado\n1;Tula;Hidalgo\n2;Tula;Tamaulipas\n2;Tula;Tamaulipas\n", encoding="utf-8"
    )
    f = FuenteBuscador(
        tipo="buscador",
        motor="searxng",
        consultas=["plan {municipio} {estado}"],
        variables="m.csv",
        columna_lugar="clave",
    )
    assert consultas(f, tmp_path) == [("plan Tula Hidalgo", "1"), ("plan Tula Tamaulipas", "2")]

    f = FuenteBuscador(
        tipo="buscador", motor="searxng", consultas=["a {x} {y}"], variables={"x": ["1", "2"], "y": ["z"]}
    )
    assert [c for c, _ in consultas(f, tmp_path)] == ["a 1 z", "a 2 z"]


def test_consulta_wayback():
    assert _consulta_wayback("*.gob.mx") == ("gob.mx", "domain")
    assert _consulta_wayback("sitio.org/docs/*") == ("sitio.org/docs/", "prefix")
