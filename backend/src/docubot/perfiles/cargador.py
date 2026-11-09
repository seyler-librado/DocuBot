"""Encuentra, lee y valida los perfiles.

Un perfil puede ser:
    config/perfiles/<nombre>.yaml               (sus archivos, junto a él)
    config/perfiles/<nombre>/perfil.yaml        (sus archivos, en su carpeta)
Los archivos que empiezan con _ o . se ignoran.
"""

import difflib
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from docubot.perfiles.esquema import TIPOS_FUENTE, Perfil, nombres_de_campos


@dataclass
class PerfilCargado:
    archivo: Path
    huella: str = ""
    perfil: Perfil | None = None
    errores: list[str] = field(default_factory=list)
    nombre: str = ""  # el del YAML si se pudo leer; si no, el del archivo

    @property
    def valido(self) -> bool:
        return self.perfil is not None and not self.errores

    @property
    def carpeta(self) -> Path:
        return self.archivo.parent


def archivos_de_perfiles(carpeta: Path) -> list[Path]:
    if not carpeta.is_dir():
        return []
    archivos = [
        p
        for p in carpeta.iterdir()
        if p.is_file() and p.suffix in (".yaml", ".yml") and not p.name.startswith(("_", "."))
    ]
    archivos += [
        p / nombre
        for p in carpeta.iterdir()
        if p.is_dir() and not p.name.startswith(("_", "."))
        for nombre in ("perfil.yaml", "perfil.yml")
        if (p / nombre).is_file()
    ]
    return sorted(archivos)


def _nombre_de_archivo(archivo: Path) -> str:
    return archivo.parent.name if archivo.stem == "perfil" else archivo.stem


def cargar(archivo: Path) -> PerfilCargado:
    resultado = PerfilCargado(archivo=archivo, nombre=_nombre_de_archivo(archivo))
    try:
        crudo = archivo.read_bytes()
    except OSError as error:
        resultado.errores.append(f"no se pudo leer el archivo: {error}")
        return resultado
    resultado.huella = hashlib.sha256(crudo).hexdigest()

    try:
        datos = yaml.safe_load(crudo.decode("utf-8-sig"))
    except UnicodeDecodeError:
        resultado.errores.append("el archivo no está en UTF-8")
        return resultado
    except yaml.YAMLError as error:
        resultado.errores.append(_error_yaml(error))
        return resultado

    if not isinstance(datos, dict):
        resultado.errores.append("el perfil debe ser un mapa de campos (nombre:, descubrimiento:, documentos:, ...)")
        return resultado
    if isinstance(datos.get("nombre"), str):
        resultado.nombre = datos["nombre"]

    try:
        resultado.perfil = Perfil.model_validate(datos, context={"carpeta": archivo.parent})
    except ValidationError as error:
        resultado.errores = traducir(error)
    return resultado


def cargar_todos(carpeta: Path) -> list[PerfilCargado]:
    resultados = [cargar(a) for a in archivos_de_perfiles(carpeta)]
    por_nombre: dict[str, list[PerfilCargado]] = {}
    for r in resultados:
        por_nombre.setdefault(r.nombre, []).append(r)
    for nombre, repetidos in por_nombre.items():
        if len(repetidos) > 1:
            otros = ", ".join(r.archivo.name for r in repetidos)
            for r in repetidos:
                r.errores.append(f"nombre: '{nombre}' está repetido en {otros}")
    return resultados


# --- mensajes -----------------------------------------------------------------


def _error_yaml(error: yaml.YAMLError) -> str:
    marca = getattr(error, "problem_mark", None)
    problema = getattr(error, "problem", None) or str(error)
    if marca is not None:
        return f"YAML mal formado en la línea {marca.line + 1}, columna {marca.column + 1}: {problema}"
    return f"YAML mal formado: {problema}"


def _ruta(loc: tuple[Any, ...]) -> str:
    partes: list[str] = []
    anterior: Any = None
    for x in loc:
        # en las fuentes, Pydantic agrega el 'tipo' a la ruta: fuentes[1].buscador.consultas
        if isinstance(anterior, int) and x in TIPOS_FUENTE:
            anterior = x
            continue
        if isinstance(x, int):
            partes.append(f"[{x}]")
        else:
            partes.append(("." if partes else "") + str(x))
        anterior = x
    return "".join(partes) or "(perfil)"


def _lista(valores: Any) -> str:
    if isinstance(valores, str):  # Pydantic lo da como "'a', 'b' or 'c'"
        return valores.replace("'", "").replace(" or ", ", ")
    return ", ".join(str(v) for v in valores)


def _mensaje(e: dict[str, Any]) -> str:
    tipo, ctx, entrada = e["type"], e.get("ctx") or {}, e.get("input")
    match tipo:
        case "missing":
            return "falta este campo"
        case "extra_forbidden":
            campo = str(e["loc"][-1])
            parecidos = difflib.get_close_matches(campo, nombres_de_campos(), n=1, cutoff=0.7)
            sugerencia = f"; ¿quisiste decir '{parecidos[0]}'?" if parecidos else ""
            return f"campo desconocido{sugerencia}"
        case "union_tag_invalid":
            return f"tipo desconocido '{ctx.get('tag')}'; usa uno de: {_lista(TIPOS_FUENTE)}"
        case "union_tag_not_found":
            return f"falta 'tipo' ({_lista(TIPOS_FUENTE)})"
        case "literal_error":
            return f"valor no válido '{entrada}'; usa uno de: {_lista(ctx.get('expected', ''))}"
        case "string_pattern_mismatch":
            return "usa solo minúsculas, números, - y _ (2 a 100 caracteres)"
        case "greater_than_equal":
            return f"debe ser mayor o igual a {ctx.get('ge')}"
        case "greater_than":
            return f"debe ser mayor que {ctx.get('gt')}"
        case "less_than_equal":
            return f"debe ser menor o igual a {ctx.get('le')}"
        case "less_than":
            return f"debe ser menor que {ctx.get('lt')}"
        case "int_parsing" | "int_type" | "int_from_float":
            return "debe ser un número entero"
        case "float_parsing" | "float_type":
            return "debe ser un número"
        case "bool_parsing" | "bool_type":
            return "debe ser true o false"
        case "string_type":
            return "debe ser texto"
        case "list_type":
            return "debe ser una lista"
        case "dict_type" | "model_type" | "model_attributes_type":
            return "debe ser un mapa de campos"
        case "too_short":
            return f"necesita al menos {ctx.get('min_length')} elemento(s)"
        case "url_parsing" | "url_scheme" | "url_type":
            return f"URL inválida '{entrada}'"
        case "value_error" | "assertion_error":
            return str(ctx.get("error", e["msg"]))
        case _:
            return e["msg"]


def traducir(error: ValidationError) -> list[str]:
    mensajes = []
    for e in error.errors(include_url=False):
        loc = e["loc"]
        # los errores de unión sin discriminador repiten cada rama; basta el primero
        mensaje = f"{_ruta(loc)}: {_mensaje(e)}"
        if mensaje not in mensajes:
            mensajes.append(mensaje)
    return mensajes
