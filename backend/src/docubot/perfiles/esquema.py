"""Esquema de un perfil YAML.

Un perfil dice QUÉ buscar: dominios, fuentes de descubrimiento, qué documentos
cuentan y qué campos llenar en su ficha. Los campos desconocidos son error
(así un error de escritura no pasa desapercibido).

Las rutas de archivos (CSV de variables, catálogos...) son relativas a la
carpeta del perfil. Para revisar que existan, la validación recibe la carpeta
en el contexto: Perfil.model_validate(datos, context={"carpeta": Path(...)}).
"""

import csv
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationInfo,
    field_validator,
    model_validator,
)

NOMBRE_PERFIL = r"^[a-z0-9][a-z0-9_-]{1,99}$"
CLAVE = re.compile(r"^[A-Za-z0-9_]+$")
CAMPO = re.compile(r"^[a-z][a-z0-9_]*$")
PATRON_DOMINIO = re.compile(r"^(\*\.)?([a-z0-9-]+\.)*[a-z0-9-]+$")
MARCADOR = re.compile(r"\{(\w+)\}")


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- utilidades de validación -------------------------------------------------


def _carpeta(info: ValidationInfo) -> Path | None:
    return (info.context or {}).get("carpeta")


def encabezado_csv(ruta: Path) -> list[str]:
    """Columnas de un CSV (acepta coma, punto y coma o tabulador; ignora BOM)."""
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        muestra = f.read(8192)
    if not muestra.strip():
        return []
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    primera = next(csv.reader(muestra.splitlines(), dialecto), [])
    return [c.strip() for c in primera]


def _revisar_archivo(nombre: str | None, info: ValidationInfo) -> str | None:
    carpeta = _carpeta(info)
    if nombre and carpeta is not None and not (carpeta / nombre).is_file():
        raise ValueError(f"no existe el archivo '{nombre}' (se busca junto al perfil)")
    return nombre


Archivo = Annotated[str, AfterValidator(_revisar_archivo)]


def _columnas(nombre: str, info: ValidationInfo) -> list[str] | None:
    """Columnas del CSV, o None si no se puede revisar (sin carpeta en el contexto)."""
    carpeta = _carpeta(info)
    if carpeta is None or not (carpeta / nombre).is_file():
        return None
    return encabezado_csv(carpeta / nombre)


def _exigir_columnas(nombre: str, requeridas: list[str], info: ValidationInfo) -> None:
    columnas = _columnas(nombre, info)
    if columnas is None:
        return
    faltan = [c for c in requeridas if c not in columnas]
    if faltan:
        raise ValueError(
            f"'{nombre}' no tiene la(s) columna(s) {', '.join(faltan)}; tiene: {', '.join(columnas) or '(vacío)'}"
        )


# --- descubrimiento -----------------------------------------------------------


class Dominios(Modelo):
    """Dominios permitidos y bloqueados. 'sitio.org' y '*.sitio.org' incluyen sus subdominios.

    Si `permitir` está vacío, se permite cualquier dominio (salvo los bloqueados).
    """

    permitir: list[str] = []
    bloquear: list[str] = []

    @field_validator("permitir", "bloquear")
    @classmethod
    def _patrones(cls, valores: list[str]) -> list[str]:
        limpios = []
        for v in valores:
            p = v.strip().lower().removeprefix("http://").removeprefix("https://").rstrip("/")
            if not PATRON_DOMINIO.match(p):
                raise ValueError(f"patrón de dominio inválido '{v}': usa algo como *.gob.mx o sitio.org")
            limpios.append(p)
        return limpios


class FuenteSemillas(Modelo):
    """Páginas de inicio que se exploran directamente."""

    tipo: Literal["semillas"]
    urls: list[HttpUrl] = Field(min_length=1)


class FuenteListaDominios(Modelo):
    """Un CSV con dominios a explorar (una fila por sitio)."""

    tipo: Literal["lista_dominios"]
    archivo: Archivo
    columna_dominio: str = "dominio"
    columna_lugar: str | None = None  # clave del catálogo de geografía

    @model_validator(mode="after")
    def _columnas(self, info: ValidationInfo) -> "FuenteListaDominios":
        requeridas = [self.columna_dominio] + ([self.columna_lugar] if self.columna_lugar else [])
        _exigir_columnas(self.archivo, requeridas, info)
        return self


class FuenteBuscador(Modelo):
    """Consultas a un buscador. Con `variables` se genera una consulta por combinación o por fila.

    - variables como mapa: {tema: [a, b], estado: [x, y]} → todas las combinaciones
    - variables como archivo CSV: una consulta por fila; las columnas son las variables
    """

    tipo: Literal["buscador"]
    motor: Literal["searxng", "brave", "serper", "serpapi"]
    consultas: list[str] = Field(min_length=1)
    variables: dict[str, list[str]] | str | None = None
    usar: Literal["dominios", "documentos"] = "dominios"
    max_resultados: int = Field(20, ge=1, le=100)
    columna_lugar: str | None = None

    @field_validator("variables")
    @classmethod
    def _variables(cls, v: Any, info: ValidationInfo) -> Any:
        if isinstance(v, str):
            _revisar_archivo(v, info)
        elif isinstance(v, dict):
            for nombre, valores in v.items():
                if not valores:
                    raise ValueError(f"la variable '{nombre}' no tiene valores")
        return v

    @model_validator(mode="after")
    def _marcadores(self, info: ValidationInfo) -> "FuenteBuscador":
        usados = {m for c in self.consultas for m in MARCADOR.findall(c)}
        if isinstance(self.variables, dict):
            definidas: list[str] | None = list(self.variables)
        elif isinstance(self.variables, str):
            definidas = _columnas(self.variables, info)
        else:
            definidas = []
        if definidas is not None:
            faltan = sorted(usados - set(definidas))
            if faltan:
                donde = f"columnas de '{self.variables}'" if isinstance(self.variables, str) else "variables"
                raise ValueError(
                    f"las consultas usan {', '.join('{' + f + '}' for f in faltan)} pero no están en {donde}"
                )
        if self.columna_lugar:
            if not isinstance(self.variables, str):
                raise ValueError("columna_lugar solo aplica cuando variables es un archivo CSV")
            if definidas is not None and self.columna_lugar not in definidas:
                raise ValueError(f"'{self.variables}' no tiene la columna '{self.columna_lugar}'")
        return self


class FuenteCommonCrawl(Modelo):
    """Índice público de Common Crawl: URLs ya rastreadas, sin hacer crawling propio."""

    tipo: Literal["commoncrawl"]
    patron: str  # p. ej. *.gob.mx
    mime: str = "application/pdf"
    indices: int = Field(1, ge=1, le=12)  # cuántos rastreos recientes consultar
    limite: int = Field(10_000, ge=1)


class FuenteWayback(Modelo):
    """Índice del Internet Archive (Wayback Machine)."""

    tipo: Literal["wayback"]
    patron: str
    mime: str = "application/pdf"
    limite: int = Field(10_000, ge=1)


Fuente = Annotated[
    FuenteSemillas | FuenteListaDominios | FuenteBuscador | FuenteCommonCrawl | FuenteWayback,
    Field(discriminator="tipo"),
]
TIPOS_FUENTE = ("semillas", "lista_dominios", "buscador", "commoncrawl", "wayback")


class Exploracion(Modelo):
    """Cómo recorrer cada sitio encontrado."""

    sitemap: bool = True
    profundidad: int = Field(2, ge=0, le=10)
    max_paginas: int = Field(40, ge=1, le=10_000)
    tiempo_max_s: int = Field(300, ge=10)
    secciones_prioritarias: list[str] = []  # palabras en la URL o el enlace que se visitan primero
    javascript: bool = False  # usar navegador para sitios hechos en JavaScript


class Descubrimiento(Modelo):
    dominios: Dominios = Dominios()
    fuentes: list[Fuente] = Field(min_length=1)
    exploracion: Exploracion = Exploracion()


# --- documentos ---------------------------------------------------------------


class TipoDocumento(Modelo):
    nombre: str
    patrones: list[str] = []  # expresiones regulares (sin distinguir mayúsculas)
    palabras: list[str] = []  # palabras o frases literales

    @field_validator("patrones")
    @classmethod
    def _regex(cls, patrones: list[str]) -> list[str]:
        for p in patrones:
            try:
                re.compile(p, re.IGNORECASE)
            except re.error as error:
                raise ValueError(f"expresión regular inválida '{p}': {error}") from None
        return patrones

    @model_validator(mode="after")
    def _algo(self) -> "TipoDocumento":
        if not self.patrones and not self.palabras:
            raise ValueError("define al menos un patrón o una palabra")
        return self


class Documentos(Modelo):
    extensiones: list[str] = ["pdf"]
    modo: Literal["palabras", "todos"] = "palabras"
    tipos: dict[str, TipoDocumento] = {}
    excluir: list[str] = []  # palabras que descartan un enlace (formatos, trámites...)
    puntaje_minimo: int = Field(60, ge=0, le=100)
    tamano_max_mb: int | None = Field(None, gt=0)  # si no, el global de almacen

    @field_validator("extensiones")
    @classmethod
    def _extensiones(cls, v: list[str]) -> list[str]:
        return [e.strip().lower().lstrip(".") for e in v if e.strip()]

    @field_validator("tipos")
    @classmethod
    def _claves(cls, v: dict[str, TipoDocumento]) -> dict[str, TipoDocumento]:
        for clave in v:
            if not CLAVE.match(clave):
                raise ValueError(f"clave de tipo inválida '{clave}': usa letras, números y _")
        return v

    @model_validator(mode="after")
    def _modo(self) -> "Documentos":
        if self.modo == "palabras" and not self.tipos:
            raise ValueError("con modo: palabras define al menos un tipo en tipos (o usa modo: todos)")
        return self


# --- fichas -------------------------------------------------------------------


class Campo(Modelo):
    tipo: Literal["texto", "fecha", "numero", "opcion", "lista", "lugar"] = "texto"
    requerido: bool = False
    opciones: list[str] = []
    descripcion: str = ""  # se le da a la IA como guía

    @model_validator(mode="after")
    def _opciones(self) -> "Campo":
        if self.tipo == "opcion" and not self.opciones:
            raise ValueError("un campo de tipo opcion necesita opciones")
        if self.opciones and self.tipo not in ("opcion", "lista"):
            raise ValueError("opciones solo aplica a campos de tipo opcion o lista")
        return self


class Fichas(Modelo):
    ia: bool = True
    campos: dict[str, Campo] = {}
    instrucciones: str = ""  # contexto extra para la IA

    @field_validator("campos")
    @classmethod
    def _nombres(cls, v: dict[str, Campo]) -> dict[str, Campo]:
        for nombre in v:
            if not CAMPO.match(nombre):
                raise ValueError(f"nombre de campo inválido '{nombre}': usa minúsculas, números y _")
        return v


# --- geografía, referencia, red ----------------------------------------------


class Geografia(Modelo):
    """Catálogo de lugares. El CSV necesita las columnas clave, nombre, nivel
    (opcionales: padre, alias separados por |, lat, lon)."""

    catalogo: Archivo
    poligonos: Archivo | None = None  # GeoJSON; la clave de cada lugar en properties.<campo_clave>
    campo_clave: str = "clave"
    nombre: str | None = Field(None, pattern=r"^[a-z0-9][a-z0-9_-]{0,99}$")  # si no, el nombre del archivo
    niveles: list[str] = []

    @property
    def identificador(self) -> str:
        """Con qué nombre se guarda el catálogo en la base (varios perfiles pueden compartirlo)."""
        return self.nombre or Path(self.catalogo).stem.lower()

    @model_validator(mode="after")
    def _columnas(self, info: ValidationInfo) -> "Geografia":
        _exigir_columnas(self.catalogo, ["clave", "nombre", "nivel"], info)
        return self


CAMPOS_REFERENCIA = ("url", "tipo", "lugar", "sha256")


class Referencia(Modelo):
    """Lo que ya se tiene: sirve para marcar como 'nuevo' lo que no está aquí.

    `llave` son las columnas que identifican un documento; cada una debe ser
    url, tipo, lugar o sha256, y existir en el CSV.
    """

    archivo: Archivo
    llave: list[str] = Field(min_length=1)

    @field_validator("llave")
    @classmethod
    def _campos(cls, v: list[str]) -> list[str]:
        malos = [c for c in v if c not in CAMPOS_REFERENCIA]
        if malos:
            raise ValueError(f"{', '.join(malos)} no se puede comparar; usa: {', '.join(CAMPOS_REFERENCIA)}")
        return v

    @model_validator(mode="after")
    def _columnas(self, info: ValidationInfo) -> "Referencia":
        _exigir_columnas(self.archivo, self.llave, info)
        return self


class RedPerfil(Modelo):
    """Ajustes de red propios del perfil (si no, los globales)."""

    peticiones_por_segundo_por_dominio: float | None = Field(None, gt=0)
    respetar_robots: bool | None = None


# --- perfil -------------------------------------------------------------------


class Perfil(Modelo):
    nombre: str = Field(pattern=NOMBRE_PERFIL)
    descripcion: str = ""
    descubrimiento: Descubrimiento
    documentos: Documentos
    fichas: Fichas = Fichas()
    geografia: Geografia | None = None
    referencia: Referencia | None = None
    red: RedPerfil = RedPerfil()

    @model_validator(mode="after")
    def _geografia(self) -> "Perfil":
        usa_lugar = any(c.tipo == "lugar" for c in self.fichas.campos.values()) or any(
            getattr(f, "columna_lugar", None) for f in self.descubrimiento.fuentes
        )
        if usa_lugar and self.geografia is None:
            raise ValueError(
                "el perfil usa lugares (campo tipo lugar o columna_lugar) pero no define geografia.catalogo"
            )
        return self


def nombres_de_campos() -> set[str]:
    """Todos los nombres de campo del esquema (para sugerir correcciones)."""
    nombres: set[str] = set()
    pendientes: list[type[BaseModel]] = [Perfil]
    vistos: set[type] = set()
    while pendientes:
        modelo = pendientes.pop()
        if modelo in vistos:
            continue
        vistos.add(modelo)
        nombres.update(modelo.model_fields)
        pendientes.extend(m for m in Modelo.__subclasses__() if m not in vistos)
    return nombres
