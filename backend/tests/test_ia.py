"""Proveedores de IA contra servidores simulados."""

import json

import httpx
import pytest

from docubot import ia
from docubot.ajustes import AjustesIA
from docubot.ia.base import Desborde, ErrorIA, ErrorIAPermanente
from docubot.ia.proveedores import Anthropic, Ollama, OpenAI, OpenAICompat


def proveedor(clase, manejador, **ajustes):
    p = clase(AjustesIA(**{"modelo": "m1", **ajustes}), httpx.MockTransport(manejador))
    p.espera_reintento = 0
    return p


def openai_ok(peticion: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "m1",
            "choices": [{"message": {"content": '{"titulo": "x"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


async def test_openai_compat_arma_la_peticion():
    vistas = []

    def manejador(peticion):
        vistas.append(peticion)
        return openai_ok(peticion)

    p = proveedor(OpenAICompat, manejador, url="http://srv:1234/v1/", llave="secreta", temperatura=0.2)
    r = await p.completar("sistema", "usuario", ["QUJD"])
    assert r.texto == '{"titulo": "x"}' and r.tokens_entrada == 10 and r.tokens_salida == 5
    peticion = vistas[0]
    assert str(peticion.url) == "http://srv:1234/v1/chat/completions"
    assert peticion.headers["authorization"] == "Bearer secreta"
    cuerpo = json.loads(peticion.content)
    assert cuerpo["model"] == "m1" and cuerpo["temperature"] == 0.2
    assert cuerpo["messages"][0] == {"role": "system", "content": "sistema"}
    contenido = cuerpo["messages"][1]["content"]
    assert contenido[0] == {"type": "text", "text": "usuario"}
    assert contenido[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"


async def test_ollama_usa_su_url_y_sin_llave():
    vistas = []
    p = proveedor(Ollama, lambda r: vistas.append(r) or openai_ok(r))
    await p.completar("s", "u")
    assert str(vistas[0].url) == "http://ollama:11434/v1/chat/completions"
    assert "authorization" not in vistas[0].headers


async def test_errores():
    with pytest.raises(ErrorIAPermanente, match="llave"):
        await proveedor(OpenAI, openai_ok).completar("s", "u")  # openai sin llave
    with pytest.raises(ErrorIAPermanente, match="ia.url"):
        await proveedor(OpenAICompat, openai_ok).completar("s", "u")
    with pytest.raises(ErrorIAPermanente, match="ia.modelo"):
        await proveedor(Ollama, openai_ok, modelo="").completar("s", "u")
    with pytest.raises(ErrorIAPermanente, match="rechazó la llave"):
        await proveedor(Ollama, lambda r: httpx.Response(401, text="no")).completar("s", "u")
    with pytest.raises(Desborde):
        await proveedor(Ollama, lambda r: httpx.Response(413, text="muy grande")).completar("s", "u")
    with pytest.raises(ErrorIAPermanente, match="imágenes"):
        await proveedor(Ollama, openai_ok, vision=False).completar("s", "u", ["QUJD"])


async def test_reintenta_fallas_pasajeras():
    respuestas = [httpx.Response(503, text="ocupado"), httpx.ConnectError("caído")]

    def manejador(peticion):
        if respuestas:
            r = respuestas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return openai_ok(peticion)

    r = await proveedor(Ollama, manejador, reintentos=2).completar("s", "u")
    assert r.texto
    with pytest.raises(ErrorIA, match="503"):
        await proveedor(Ollama, lambda q: httpx.Response(503), reintentos=1).completar("s", "u")


async def test_anthropic():
    vistas = []

    def manejador(peticion):
        vistas.append(peticion)
        return httpx.Response(
            200,
            json={
                "model": "m1",
                "content": [{"type": "text", "text": "hola"}],
                "usage": {"input_tokens": 3, "output_tokens": 1},
            },
        )

    r = await proveedor(Anthropic, manejador, llave="k").completar("sis", "usu", ["QUJD"])
    assert r.texto == "hola" and r.tokens_entrada == 3
    cuerpo = json.loads(vistas[0].content)
    assert vistas[0].headers["x-api-key"] == "k" and vistas[0].headers["anthropic-version"]
    assert cuerpo["system"] == "sis"
    assert cuerpo["messages"][0]["content"][0]["source"]["data"] == "QUJD"
    assert cuerpo["messages"][0]["content"][-1] == {"type": "text", "text": "usu"}


async def test_extension_propia(tmp_path):
    (tmp_path / "mia.py").write_text(
        "from docubot.ia.base import Proveedor, Respuesta\n"
        "class MiIA(Proveedor):\n"
        "    nombre = 'mia'\n"
        "    async def _completar(self, sistema, usuario, imagenes):\n"
        "        return Respuesta(f'eco: {usuario}')\n",
        encoding="utf-8",
    )
    clase = ia.cargar_extension("mia.py:MiIA", tmp_path)
    r = await clase(AjustesIA(proveedor="mia.py:MiIA")).completar("s", "hola")
    assert r.texto == "eco: hola"
    with pytest.raises(ErrorIAPermanente):
        ia.cargar_extension("no-existe.py:X", tmp_path)
    with pytest.raises(ValueError):
        AjustesIA(proveedor="chatgpt")
