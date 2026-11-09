"""Ajustes globales: config/docubot.yaml + variables de entorno + .env.

Prioridad (de mayor a menor): argumentos, entorno, .env, docubot.yaml, valores por omisión.
Las variables usan el prefijo DOCUBOT_ y doble guion bajo para entrar a una sección:
DOCUBOT_TRABAJADORES__DESCARGA=8.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

PROVEEDORES_IA = ("ninguno", "ollama", "openai", "openai_compat", "anthropic")


class AjustesIA(BaseModel):
    """Proveedor de IA para las fichas.

    `proveedor` es uno de PROVEEDORES_IA o una extensión propia
    "archivo.py:Clase" en config/extensiones/ (ver su README).
    """

    proveedor: str = "ninguno"
    modelo: str = ""
    url: str = ""
    llave: SecretStr | None = None
    temperatura: float = Field(0.0, ge=0, le=2)
    max_tokens_salida: int = Field(1500, ge=100, le=32000)
    timeout: float = Field(180, gt=0)
    reintentos: int = Field(2, ge=0, le=10)
    vision: bool = True  # mandar imágenes de las páginas escaneadas (si el modelo las lee)
    paginas: int = Field(12, ge=1, le=200)  # páginas de texto que se le dan
    paginas_imagen: int = Field(3, ge=1, le=20)  # páginas escaneadas que se le mandan como imagen
    max_caracteres: int = Field(16000, ge=1000)  # tope del texto que se le da

    @field_validator("proveedor")
    @classmethod
    def _proveedor(cls, v: str) -> str:
        v = v.strip()
        if v in PROVEEDORES_IA or (":" in v and v.split(":", 1)[0].endswith(".py")):
            return v
        raise ValueError(f"proveedor de IA desconocido '{v}': usa {', '.join(PROVEEDORES_IA)} o 'archivo.py:Clase'")


class AjustesTrabajadores(BaseModel):
    """Tareas simultáneas por etapa del pipeline."""

    descubrimiento: int = Field(2, ge=0, le=64)
    exploracion: int = Field(4, ge=0, le=64)
    descarga: int = Field(4, ge=0, le=64)
    extraccion: int = Field(2, ge=0, le=64)
    ia: int = Field(1, ge=0, le=16)


class AjustesRed(BaseModel):
    user_agent: str = "DocuBot/0.1 (+https://github.com/seyler-librado/DocuBot)"
    peticiones_por_segundo_por_dominio: float = Field(1.0, gt=0)
    simultaneas_por_dominio: int = Field(2, ge=1, le=16)
    respetar_robots: bool = True
    timeout: float = Field(30, gt=0)
    reintentos: int = Field(3, ge=0, le=10)
    max_redirecciones: int = Field(10, ge=0, le=30)
    max_mb_pagina: int = Field(10, gt=0)  # páginas HTML; los documentos usan almacen.tamano_max_mb
    verificar_tls: bool = True
    # muchos sitios públicos tienen certificados vencidos o incompletos:
    # si falla la verificación, reintenta sin verificar y lo anota
    reintentar_sin_tls: bool = True


class AjustesBuscadores(BaseModel):
    """Buscadores para las fuentes 'buscador'. Las llaves van en .env."""

    searxng_url: str = "http://searxng:8080"
    brave_llave: SecretStr | None = None
    serper_llave: SecretStr | None = None
    serpapi_llave: SecretStr | None = None
    pais: str = ""  # código de país para los resultados (p. ej. mx); vacío = sin preferencia
    idioma: str = "es"


PROVEEDORES_EMBEDDINGS = ("ninguno", "local", "ollama", "openai", "openai_compat")


class AjustesBusqueda(BaseModel):
    """Búsqueda por tema: el texto se parte en fragmentos y cada uno se vuelve un vector.

    `embeddings: local` usa un modelo chico multilingüe que corre en CPU dentro
    del contenedor (se descarga una vez, ~220 MB). Con ollama/openai/openai_compat
    se usa el endpoint /v1/embeddings de ese servidor.
    """

    embeddings: str = "ninguno"
    modelo: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    url: str = ""
    llave: SecretStr | None = None
    tamano_fragmento: int = Field(900, ge=200, le=8000)  # caracteres
    solape: int = Field(150, ge=0, le=2000)
    max_fragmentos: int = Field(400, ge=1, le=20000)  # por documento (los de las primeras páginas)
    # por tema, un documento entra si se parece al menos esto (0 a 1) y no está muy lejos del mejor
    similitud_minima: float = Field(0.45, ge=0, le=1)
    ventana_similitud: float = Field(0.2, ge=0, le=1)
    carpeta_modelos: Path = Path("/datos/modelos")

    @field_validator("embeddings")
    @classmethod
    def _embeddings(cls, v: str) -> str:
        if v not in PROVEEDORES_EMBEDDINGS:
            raise ValueError(f"embeddings desconocido '{v}': usa {', '.join(PROVEEDORES_EMBEDDINGS)}")
        return v


class AjustesMapa(BaseModel):
    """Mapa base de la interfaz. Los polígonos del catálogo se dibujan encima (se ven aun sin internet)."""

    teselas: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    atribucion: str = "© OpenStreetMap"


class AjustesAlmacen(BaseModel):
    carpeta: Path = Path("/datos/almacen")
    tamano_max_mb: int = Field(200, gt=0)
    # si un documento ya no está (404, página en lugar de PDF, incompleto),
    # intenta la copia del Internet Archive
    respaldo_wayback: bool = True


def ruta_config() -> Path:
    return Path(os.environ.get("DOCUBOT_CONFIG", "config/docubot.yaml"))


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUBOT_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    base_datos_url: str = "postgresql+psycopg://docubot:docubot@localhost:5433/docubot"
    carpeta_perfiles: Path = Path("config/perfiles")
    carpeta_extensiones: Path = Path("config/extensiones")
    ia: AjustesIA = AjustesIA()
    trabajadores: AjustesTrabajadores = AjustesTrabajadores()
    red: AjustesRed = AjustesRed()
    buscadores: AjustesBuscadores = AjustesBuscadores()
    mapa: AjustesMapa = AjustesMapa()
    busqueda: AjustesBusqueda = AjustesBusqueda()
    almacen: AjustesAlmacen = AjustesAlmacen()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml = YamlConfigSettingsSource(settings_cls, yaml_file=ruta_config())
        return (init_settings, env_settings, dotenv_settings, yaml)

    def publicos(self) -> dict:
        """Lo que se puede mostrar en la interfaz (sin llaves ni contraseñas)."""
        datos = self.model_dump(mode="json", exclude={"base_datos_url"})
        datos["ia"].pop("llave", None)
        datos["busqueda"].pop("llave", None)
        datos["ia"]["con_llave"] = self.ia.llave is not None
        if ":" in self.ia.proveedor:  # extensión propia: no mostrar su dirección
            datos["ia"]["url"] = "(extensión)" if self.ia.url else ""
        b = self.buscadores
        datos["buscadores"] = {
            "searxng_url": b.searxng_url,
            "pais": b.pais,
            "idioma": b.idioma,
            "con_llave": {
                "brave": b.brave_llave is not None,
                "serper": b.serper_llave is not None,
                "serpapi": b.serpapi_llave is not None,
            },
        }
        return datos


@lru_cache
def obtener_ajustes() -> Ajustes:
    return Ajustes()
