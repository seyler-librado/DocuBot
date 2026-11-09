import pytest

from docubot.filtros.dominios import FiltroDominios
from docubot.red.urls import clave_url, host_de, origen_de


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://www.Sitio.gob.mx/docs/", "http://sitio.gob.mx/docs"),
        ("https://sitio.gob.mx/a.pdf#pagina=2", "https://sitio.gob.mx/a.pdf"),
        ("https://sitio.gob.mx/a.pdf?utm_source=x&id=3", "https://sitio.gob.mx/a.pdf?id=3"),
        ("https://sitio.gob.mx:443/a", "https://sitio.gob.mx/a"),
        ("https://sitio.gob.mx//a//b.pdf", "https://sitio.gob.mx/a/b.pdf"),
    ],
)
def test_clave_url_iguala_variantes(a, b):
    assert clave_url(a) == clave_url(b)


def test_clave_url_distingue_lo_que_importa():
    assert clave_url("https://s.mx/ver?id=1") != clave_url("https://s.mx/ver?id=2")
    assert clave_url("https://s.mx:8080/a") != clave_url("https://s.mx/a")


def test_host_y_origen():
    assert host_de("https://WWW.Sitio.gob.mx./x") == "www.sitio.gob.mx"
    assert host_de("no es url") == ""
    assert origen_de("https://s.mx:8443/a/b?c") == "https://s.mx:8443"


def test_filtro_de_dominios():
    f = FiltroDominios(permitir=["*.gob.mx", "inegi.org.mx"], bloquear=["spam.gob.mx"])
    assert f.permitido("https://tulancingo.gob.mx/x.pdf")
    assert f.permitido("gob.mx")
    assert f.permitido("https://www.inegi.org.mx/")
    assert not f.permitido("https://datos.spam.gob.mx/")
    assert not f.permitido("https://gob.mx.malo.com/")
    assert not f.permitido("https://ejemplo.com/")
    assert FiltroDominios().permitido("https://cualquiera.org/")
