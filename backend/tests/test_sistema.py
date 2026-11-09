import httpx
from sqlalchemy import inspect

from docubot.ajustes import Ajustes
from docubot.db.modelos import Base
from docubot.main import app


async def test_salud_reporta_base_y_extensiones():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/salud")
    assert r.status_code == 200
    datos = r.json()
    assert datos["ok"] is True
    base = datos["base_datos"]
    assert base["postgis"] and base["vector"] and base["migracion"]


async def test_ajustes_publicos_no_exponen_llaves(monkeypatch):
    monkeypatch.setenv("DOCUBOT_IA__LLAVE", "secreta")
    publicos = Ajustes().publicos()
    assert "secreta" not in str(publicos)
    assert publicos["ia"]["con_llave"] is True
    assert "base_datos_url" not in publicos


def test_yaml_y_entorno(tmp_path, monkeypatch):
    archivo = tmp_path / "docubot.yaml"
    archivo.write_text("trabajadores:\n  descarga: 7\n  ia: 2\nia:\n  proveedor: ollama\n")
    monkeypatch.setenv("DOCUBOT_CONFIG", str(archivo))
    monkeypatch.setenv("DOCUBOT_TRABAJADORES__IA", "3")
    monkeypatch.delenv("DOCUBOT_IA__PROVEEDOR", raising=False)
    a = Ajustes()
    assert a.trabajadores.descarga == 7  # del YAML
    assert a.trabajadores.ia == 3  # el entorno gana
    assert a.ia.proveedor == "ollama"


async def test_migraciones_cubren_todos_los_modelos(sesiones):
    async with sesiones() as s:
        conexion = await s.connection()
        tablas = await conexion.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert set(Base.metadata.tables) <= tablas
