import textwrap
from pathlib import Path

import pytest
from sqlalchemy import select

from docubot.db.modelos import Perfil as PerfilBD
from docubot.perfiles import archivos_de_perfiles, cargar, cargar_todos
from docubot.perfiles.sincronizar import sincronizar

MINIMO = """
nombre: prueba
descubrimiento:
  fuentes:
    - tipo: semillas
      urls: [https://ejemplo.gob.mx/]
documentos:
  modo: todos
"""


def escribir(carpeta: Path, nombre: str, texto: str) -> Path:
    archivo = carpeta / nombre
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(textwrap.dedent(texto), encoding="utf-8")
    return archivo


def errores_de(carpeta: Path, texto: str) -> list[str]:
    return cargar(escribir(carpeta, "p.yaml", texto)).errores


def test_minimo_valido(tmp_path):
    c = cargar(escribir(tmp_path, "p.yaml", MINIMO))
    assert c.valido, c.errores
    assert c.perfil.descubrimiento.exploracion.profundidad == 2
    assert len(c.huella) == 64


def test_ejemplo_del_repositorio_es_valido():
    ejemplo = Path("/app/config/perfiles/ejemplo.yaml")
    if not ejemplo.exists():
        pytest.skip("config/ no está montado")
    c = cargar(ejemplo)
    assert c.valido, c.errores


def test_campo_mal_escrito_sugiere_correccion(tmp_path):
    texto = MINIMO.replace("  fuentes:", "  fuentess:")
    errores = errores_de(tmp_path, texto)
    assert any("descubrimiento.fuentess: campo desconocido; ¿quisiste decir 'fuentes'?" in e for e in errores)
    assert any("descubrimiento.fuentes: falta este campo" in e for e in errores)


def test_tipo_de_fuente_desconocido(tmp_path):
    errores = errores_de(tmp_path, MINIMO.replace("tipo: semillas", "tipo: google"))
    assert errores == [
        "descubrimiento.fuentes[0]: tipo desconocido 'google'; "
        "usa uno de: semillas, lista_dominios, buscador, commoncrawl, wayback"
    ]


def test_valor_fuera_de_lista(tmp_path):
    texto = MINIMO.replace(
        "    - tipo: semillas\n      urls: [https://ejemplo.gob.mx/]",
        "    - tipo: buscador\n      motor: google\n      consultas: [plan]",
    )
    assert errores_de(tmp_path, texto) == [
        "descubrimiento.fuentes[0].motor: valor no válido 'google'; usa uno de: searxng, brave, serper, serpapi"
    ]


def test_marcador_sin_variable(tmp_path):
    texto = MINIMO.replace(
        "    - tipo: semillas\n      urls: [https://ejemplo.gob.mx/]",
        "    - tipo: buscador\n      motor: searxng\n      consultas: ['plan {municipio} {estado}']\n"
        "      variables: {estado: [Hidalgo]}",
    )
    [error] = errores_de(tmp_path, texto)
    assert error.startswith("descubrimiento.fuentes[0]:")
    assert "{municipio}" in error and "{estado}" not in error


def test_variables_desde_csv_revisa_columnas(tmp_path):
    escribir(tmp_path, "municipios.csv", "clave;municipio;estado\n13077;Tulancingo;Hidalgo\n")
    base = MINIMO.replace(
        "    - tipo: semillas\n      urls: [https://ejemplo.gob.mx/]",
        "    - tipo: buscador\n      motor: brave\n      consultas: ['plan {municipio} {estado}']\n"
        "      variables: municipios.csv\n      columna_lugar: clave",
    )
    geografia = "geografia:\n  catalogo: lugares.csv\n"
    escribir(tmp_path, "lugares.csv", "clave,nombre,nivel\n13077,Tulancingo,municipio\n")
    assert cargar(escribir(tmp_path, "p.yaml", base + geografia)).valido

    errores = errores_de(tmp_path, base.replace("{estado}", "{entidad}") + geografia)
    assert any("{entidad}" in e and "municipios.csv" in e for e in errores)

    # columna_lugar sin catálogo de geografía
    assert any("geografia" in e for e in errores_de(tmp_path, base))


def test_archivo_inexistente(tmp_path):
    texto = MINIMO.replace(
        "    - tipo: semillas\n      urls: [https://ejemplo.gob.mx/]",
        "    - tipo: lista_dominios\n      archivo: no-existe.csv",
    )
    [error] = errores_de(tmp_path, texto)
    assert "descubrimiento.fuentes[0].archivo" in error and "no-existe.csv" in error


def test_regex_invalida_y_modo_palabras_sin_tipos(tmp_path):
    texto = MINIMO.replace(
        "  modo: todos",
        "  tipos:\n    PLAN:\n      nombre: Plan\n      patrones: ['plan(']",
    )
    [error] = errores_de(tmp_path, texto)
    assert error.startswith("documentos.tipos.PLAN.patrones:") and "plan(" in error

    [error] = errores_de(tmp_path, MINIMO.replace("  modo: todos", "  modo: palabras"))
    assert "al menos un tipo" in error


def test_valores_fuera_de_rango_y_opciones(tmp_path):
    texto = MINIMO + textwrap.dedent(
        """
        fichas:
          campos:
            tema: {tipo: opcion}
        """
    )
    texto = texto.replace("documentos:", "  exploracion: {profundidad: 50}\ndocumentos:")
    errores = errores_de(tmp_path, texto)
    assert "descubrimiento.exploracion.profundidad: debe ser menor o igual a 10" in errores
    assert any(e.startswith("fichas.campos.tema:") and "opciones" in e for e in errores)


def test_yaml_mal_formado_da_linea(tmp_path):
    [error] = errores_de(tmp_path, "nombre: x\ndescubrimiento: [a\n")
    assert error.startswith("YAML mal formado en la línea")


def test_descubre_archivos_y_carpetas_y_detecta_repetidos(tmp_path):
    escribir(tmp_path, "uno.yaml", MINIMO)
    escribir(tmp_path, "dos/perfil.yaml", MINIMO)
    escribir(tmp_path, "_borrador.yaml", MINIMO)
    assert [p.relative_to(tmp_path).as_posix() for p in archivos_de_perfiles(tmp_path)] == [
        "dos/perfil.yaml",
        "uno.yaml",
    ]
    cargados = cargar_todos(tmp_path)
    assert all(not c.valido and "repetido" in c.errores[-1] for c in cargados)


async def test_sincronizar_crea_actualiza_y_reporta(tmp_path, sesiones):
    archivo = escribir(tmp_path, "uno.yaml", MINIMO)
    escribir(tmp_path, "malo.yaml", "nombre: malo\n")

    async with sesiones() as s:
        r = await sincronizar(s, cargar_todos(tmp_path))
        await s.commit()
        assert r.creados == ["prueba"] and list(r.invalidos) == ["malo"]

        r = await sincronizar(s, cargar_todos(tmp_path))
        assert r.sin_cambios == ["prueba"]

        archivo.write_text(MINIMO + "descripcion: otra\n", encoding="utf-8")
        r = await sincronizar(s, cargar_todos(tmp_path))
        await s.commit()
        assert r.actualizados == ["prueba"]
        fila = await s.scalar(select(PerfilBD).where(PerfilBD.nombre == "prueba"))
        assert fila.descripcion == "otra"
        assert fila.config["documentos"]["modo"] == "todos"

        archivo.unlink()
        r = await sincronizar(s, cargar_todos(tmp_path))
        assert r.sin_archivo == ["prueba"]
