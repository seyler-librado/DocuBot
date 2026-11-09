"""Esquema de la base de datos.

Recorrido de un documento:
    perfil → corrida → sitio → candidato (URL encontrada) → documento (PDF, por sha256)
    → texto → ficha (campos del perfil) → documento_lugares (dónde aplica)

`tareas` es la cola del pipeline: cada etapa toma sus tareas pendientes de ahí.
"""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONVENCION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# Búsqueda de texto completo: español, sin acentos (configuración docubot_es, ver migración).
# El cuerpo se indexa hasta 400 mil caracteres (un tsvector no admite más de 1 MB).
TSV_TEXTO = "to_tsvector('docubot_es'::regconfig, left(contenido, 400000))"
TSV_FICHA = (
    "setweight(to_tsvector('docubot_es'::regconfig, coalesce(campos ->> 'titulo', campos ->> 'nombre', '')), 'A') || "
    "setweight(jsonb_to_tsvector('docubot_es'::regconfig, campos, '[\"string\"]'), 'B')"
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION)


def _ahora() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _json() -> Mapped[dict[str, Any]]:
    return mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class Perfil(Base):
    """Un perfil YAML cargado: qué buscar y cómo catalogarlo."""

    __tablename__ = "perfiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    descripcion: Mapped[str] = mapped_column(Text, server_default="")
    config: Mapped[dict[str, Any]] = _json()
    huella: Mapped[str] = mapped_column(String(64), server_default="")  # sha256 del YAML
    creado: Mapped[datetime] = _ahora()
    actualizado: Mapped[datetime] = _ahora()


class Corrida(Base):
    """Una ejecución del pipeline para un perfil."""

    __tablename__ = "corridas"

    id: Mapped[int] = mapped_column(primary_key=True)
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfiles.id", ondelete="CASCADE"), index=True)
    # pendiente | corriendo | detenida | terminada | error
    estado: Mapped[str] = mapped_column(String(20), server_default="pendiente")
    parametros: Mapped[dict[str, Any]] = _json()
    contadores: Mapped[dict[str, Any]] = _json()
    error: Mapped[str | None] = mapped_column(Text)
    creada: Mapped[datetime] = _ahora()
    iniciada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Lugar(Base):
    """Un lugar de un catálogo geográfico (país, estado, municipio...).

    La identidad es (catalogo, clave), nunca el nombre: los nombres se repiten.
    """

    __tablename__ = "lugares"
    __table_args__ = (
        UniqueConstraint("catalogo", "clave"),
        Index("ix_lugares_punto", "punto", postgresql_using="gist"),
        Index("ix_lugares_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalogo: Mapped[str] = mapped_column(String(50))
    clave: Mapped[str] = mapped_column(String(50))
    nombre: Mapped[str] = mapped_column(String(300))
    alias: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    nivel: Mapped[str] = mapped_column(String(30))
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("lugares.id", ondelete="SET NULL"), index=True)
    punto: Mapped[Any | None] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    geom: Mapped[Any | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False))
    datos: Mapped[dict[str, Any]] = _json()


class Catalogo(Base):
    """Un catálogo de lugares importado (para no reimportarlo si no cambió)."""

    __tablename__ = "catalogos"

    nombre: Mapped[str] = mapped_column(String(100), primary_key=True)
    huella: Mapped[str] = mapped_column(String(64))
    lugares: Mapped[int] = mapped_column(Integer, server_default="0")
    actualizado: Mapped[datetime] = _ahora()


class Sitio(Base):
    """Un dominio que se explora o del que salieron documentos."""

    __tablename__ = "sitios"

    id: Mapped[int] = mapped_column(primary_key=True)
    dominio: Mapped[str] = mapped_column(String(255), unique=True)
    # nuevo | explorando | explorado | sin_respuesta | bloqueado
    estado: Mapped[str] = mapped_column(String(20), server_default="nuevo")
    origen: Mapped[str] = mapped_column(String(30), server_default="")  # lista | buscador | ...
    lugar_id: Mapped[int | None] = mapped_column(ForeignKey("lugares.id", ondelete="SET NULL"), index=True)
    robots_txt: Mapped[str | None] = mapped_column(Text)
    ultima_visita: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    datos: Mapped[dict[str, Any]] = _json()
    creado: Mapped[datetime] = _ahora()


class CorridaSitio(Base):
    """Un sitio que una corrida debe explorar (una sola vez aunque varias fuentes lo encuentren)."""

    __tablename__ = "corrida_sitios"

    corrida_id: Mapped[int] = mapped_column(ForeignKey("corridas.id", ondelete="CASCADE"), primary_key=True)
    sitio_id: Mapped[int] = mapped_column(ForeignKey("sitios.id", ondelete="CASCADE"), primary_key=True, index=True)
    # pendiente | explorado | sin_respuesta | redes_sociales | estacionado | bloqueado | error
    estado: Mapped[str] = mapped_column(String(20), server_default="pendiente")
    origen: Mapped[str] = mapped_column(String(30), server_default="")
    semillas: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    lugar: Mapped[str | None] = mapped_column(String(50))  # clave del catálogo, si la fuente la trae
    paginas: Mapped[int] = mapped_column(Integer, server_default="0")
    documentos: Mapped[int] = mapped_column(Integer, server_default="0")
    segundos: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    creado: Mapped[datetime] = _ahora()
    terminado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Documento(Base):
    """Un archivo descargado. Se identifica por su contenido (sha256)."""

    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    ruta: Mapped[str] = mapped_column(Text)  # relativa a la carpeta del almacén
    bytes: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(100), server_default="application/pdf")
    paginas: Mapped[int | None] = mapped_column(Integer)
    # descargado | texto | escaneado | ilegible
    estado: Mapped[str] = mapped_column(String(20), server_default="descargado")
    creado: Mapped[datetime] = _ahora()


class Candidato(Base):
    """Una URL encontrada para un perfil. Varias URLs pueden dar el mismo documento."""

    __tablename__ = "candidatos"
    __table_args__ = (UniqueConstraint("perfil_id", "clave_url"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfiles.id", ondelete="CASCADE"))
    corrida_id: Mapped[int | None] = mapped_column(ForeignKey("corridas.id", ondelete="SET NULL"), index=True)
    sitio_id: Mapped[int | None] = mapped_column(ForeignKey("sitios.id", ondelete="SET NULL"), index=True)
    url: Mapped[str] = mapped_column(Text)
    clave_url: Mapped[str] = mapped_column(Text)  # URL normalizada para deduplicar
    fuente: Mapped[str] = mapped_column(String(30))  # semillas | buscador | crawler | ...
    ancla: Mapped[str | None] = mapped_column(Text)
    pagina_origen: Mapped[str | None] = mapped_column(Text)
    profundidad: Mapped[int | None] = mapped_column(Integer)
    tipo: Mapped[str | None] = mapped_column(String(50))
    puntaje: Mapped[int | None] = mapped_column(Integer)
    # nuevo | aceptado | rechazado | descargado | fallido
    estado: Mapped[str] = mapped_column(String(20), server_default="nuevo", index=True)
    motivo: Mapped[str | None] = mapped_column(Text)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id", ondelete="SET NULL"), index=True)
    lugar_id: Mapped[int | None] = mapped_column(ForeignKey("lugares.id", ondelete="SET NULL"), index=True)
    datos: Mapped[dict[str, Any]] = _json()
    creado: Mapped[datetime] = _ahora()
    actualizado: Mapped[datetime] = _ahora()


class Texto(Base):
    """Texto extraído de un documento."""

    __tablename__ = "textos"
    __table_args__ = (Index("ix_textos_tsv", "tsv", postgresql_using="gin"),)

    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), primary_key=True)
    contenido: Mapped[str] = mapped_column(Text)
    metodo: Mapped[str] = mapped_column(String(20))  # texto | escaneado | ilegible
    caracteres: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)  # por qué no se pudo leer
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed(TSV_TEXTO, persisted=True), deferred=True)
    creado: Mapped[datetime] = _ahora()


class Ficha(Base):
    """Los campos de un documento según un perfil (los llena la IA o una persona)."""

    __tablename__ = "fichas"
    __table_args__ = (
        UniqueConstraint("documento_id", "perfil_id"),
        Index("ix_fichas_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"))
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfiles.id", ondelete="CASCADE"), index=True)
    campos: Mapped[dict[str, Any]] = _json()
    # ok | revision | ilegible | error
    estado: Mapped[str] = mapped_column(String(20), server_default="revision")
    confianza: Mapped[str | None] = mapped_column(String(10))  # alta | media | baja
    motivos: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    modelo: Mapped[str | None] = mapped_column(String(100))
    version_prompt: Mapped[str | None] = mapped_column(String(50))
    # cómo se hizo: tipo según la IA, método (texto/imagen), segundos, tokens...
    control: Mapped[dict[str, Any]] = _json()
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed(TSV_FICHA, persisted=True), deferred=True)
    creado: Mapped[datetime] = _ahora()
    actualizado: Mapped[datetime] = _ahora()


class Fragmento(Base):
    """Un pedazo del texto de un documento con su vector, para la búsqueda por tema."""

    __tablename__ = "fragmentos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    pagina: Mapped[int | None] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(Text)
    modelo: Mapped[str] = mapped_column(String(200), index=True)
    embedding: Mapped[Any] = mapped_column(Vector())  # sin dimensión fija: depende del modelo


class DocumentoLugar(Base):
    """Dónde aplica un documento. Un documento puede tener varios lugares.

    Si es ambiguo (p. ej. un nombre de municipio que existe en varios estados),
    queda con `lugar_id` vacío, estado `ambiguo` y la lista de `candidatos`.
    """

    __tablename__ = "documento_lugares"
    __table_args__ = (UniqueConstraint("documento_id", "lugar_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    lugar_id: Mapped[int | None] = mapped_column(ForeignKey("lugares.id", ondelete="CASCADE"), index=True)
    catalogo: Mapped[str | None] = mapped_column(String(100), index=True)
    # fuente | fuente+contenido | contenido | manual
    origen: Mapped[str] = mapped_column(String(20))
    confianza: Mapped[float] = mapped_column(Float, server_default="0")
    estado: Mapped[str] = mapped_column(
        String(20), server_default="asignado"
    )  # asignado | ambiguo | revision | sin_lugar
    candidatos: Mapped[list[Any] | None] = mapped_column(JSONB)
    creado: Mapped[datetime] = _ahora()


class Tarea(Base):
    """Cola del pipeline. Los trabajadores toman tareas con FOR UPDATE SKIP LOCKED."""

    __tablename__ = "tareas"
    __table_args__ = (
        Index(
            "ix_tareas_pendientes",
            "etapa",
            "prioridad",
            "id",
            postgresql_where=text("estado = 'pendiente'"),
        ),
        # para no encolar dos veces la misma tarea (extraer, fichar...)
        Index(
            "ix_tareas_clave",
            text("(carga ->> 'clave')"),
            postgresql_where=text("estado IN ('pendiente', 'tomada')"),
        ),
        # para no encolar dos veces la descarga de un candidato
        Index(
            "ix_tareas_candidato",
            text("(carga ->> 'candidato_id')"),
            postgresql_where=text("etapa = 'descargar'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    etapa: Mapped[str] = mapped_column(String(30))
    corrida_id: Mapped[int | None] = mapped_column(ForeignKey("corridas.id", ondelete="CASCADE"), index=True)
    carga: Mapped[dict[str, Any]] = _json()
    # pendiente | tomada | hecha | fallida | cancelada
    estado: Mapped[str] = mapped_column(String(20), server_default="pendiente")
    prioridad: Mapped[int] = mapped_column(Integer, server_default="0")
    intentos: Mapped[int] = mapped_column(Integer, server_default="0")
    max_intentos: Mapped[int] = mapped_column(Integer, server_default="3")
    disponible_en: Mapped[datetime] = _ahora()
    tomada_por: Mapped[str | None] = mapped_column(String(100))
    tomada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    creada: Mapped[datetime] = _ahora()
    terminada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
