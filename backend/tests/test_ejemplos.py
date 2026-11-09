"""Los perfiles de ejemplo (y el de config/perfiles) son válidos tal como se copian."""

import shutil
from pathlib import Path

import pytest

from docubot.filtros.puntaje import Calificador
from docubot.perfiles import cargar

RAIZ = next((p for p in (Path("/app"), Path(__file__).resolve().parents[2]) if (p / "config").is_dir()), None)
EJEMPLOS = sorted((RAIZ / "ejemplos").glob("*/perfil.yaml")) if RAIZ and (RAIZ / "ejemplos").is_dir() else []


@pytest.fixture(scope="module")
def config(tmp_path_factory):
    """Una copia de config/ con los ejemplos dentro de perfiles/, como quedarían al copiarlos."""
    if not EJEMPLOS:
        pytest.skip("no están los ejemplos (ejemplos/ no montado)")
    destino = tmp_path_factory.mktemp("config")
    shutil.copytree(RAIZ / "config" / "catalogos", destino / "catalogos")
    for perfil in EJEMPLOS:
        shutil.copytree(perfil.parent, destino / "perfiles" / perfil.parent.name)
    return destino


def test_hay_ejemplos():
    if RAIZ is None:
        pytest.skip("sin config/")
    assert len(EJEMPLOS) >= 3


@pytest.mark.parametrize("nombre", [p.parent.name for p in EJEMPLOS])
def test_ejemplo_valido(config, nombre):
    c = cargar(config / "perfiles" / nombre / "perfil.yaml")
    assert c.valido, c.errores
    assert c.perfil.nombre == nombre


def test_planeacion_clasifica_nombres_reales(config):
    c = cargar(config / "perfiles" / "planeacion-municipal-mx" / "perfil.yaml")
    calificador = Calificador(c.perfil.documentos)
    casos = {
        "https://asientos.gob.mx/Archivos/02%20PLAN%20MUNICIPAL%20DE%20DESARROLLO%20ASIENTOS%202017%20-2019.pdf": "PMD",
        "https://copladem.edomex.gob.mx/PDM_2025-2027_TOLUCA.pdf": "PMD",
        "https://m.gob.mx/docs/PlanMunicipalDeDesarrollo2024.pdf": "PMD",
        "https://m.gob.mx/transparencia/Programa_Municipal_de_Desarrollo_Urbano_Pachuca.pdf": "PMDU",
        "https://m.gob.mx/Atlas_de_Riesgos_2020.pdf": "ATLAS",
        "https://m.gob.mx/POEL_municipio.pdf": "OET",
        "https://m.gob.mx/Reglamento_de_Construccion_2019.pdf": "NORMA",
        "https://m.gob.mx/carta-urbana.pdf": "ZONIF",
    }
    for url, tipo in casos.items():
        nota = calificador.calificar(url)
        assert (nota.tipo, nota.aceptado) == (tipo, True), url
    assert not calificador.calificar("https://m.gob.mx/Aviso_de_privacidad_plan_municipal_de_desarrollo.pdf").aceptado
    assert not calificador.calificar("https://m.gob.mx/acta_de_cabildo_atlas_de_riesgos.pdf").aceptado


def test_normas_clasifica_claves(config):
    c = cargar(config / "perfiles" / "normas-oficiales-mx" / "perfil.yaml")
    calificador = Calificador(c.perfil.documentos)
    assert calificador.calificar("https://www.gob.mx/NOM-001-SEMARNAT-2021.pdf").tipo == "NOM"
    assert calificador.calificar("https://www.gob.mx/NMX-C-414-ONNCCE-2017.pdf").tipo == "NMX"
