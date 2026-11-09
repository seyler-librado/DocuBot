# Arquitectura

## Servicios

```
                       ┌────────────┐
  navegador ──────────►│ web (nginx)│── archivos de la interfaz (React)
                       └─────┬──────┘
                             │ /api, /api/eventos (WebSocket)
                       ┌─────▼──────┐      LISTEN      ┌──────────────────────────┐
                       │ api        │◄─────────────────┤ db                       │
                       │ (FastAPI)  │─────────────────►│ Postgres 16              │
                       └────────────┘                  │ + PostGIS + pgvector     │
                       ┌────────────┐   tareas/NOTIFY  │                          │
                       │ worker     │◄────────────────►│ cola, datos, eventos     │
                       │ (asyncio)  │                  └──────────────────────────┘
                       └─────┬──────┘
          sitios web, buscadores, IA, modelo de vectores, almacén de archivos
```

| servicio | qué hace |
|---|---|
| `db` | todos los datos, la cola de tareas, los eventos (NOTIFY), los lugares (PostGIS) y los vectores (pgvector) |
| `migrar` | aplica las migraciones (Alembic) al arrancar y termina |
| `api` | la API REST, el WebSocket de eventos y la carga de perfiles y catálogos al arrancar |
| `worker` | corre las etapas del pipeline con N tareas a la vez por etapa |
| `web` | sirve la interfaz y pasa `/api` a la API |
| `searxng`, `ollama` | opcionales (`--profile`) |

## El pipeline

```
descubrir → explorar → descargar → extraer → fichar → ubicar
                                         └──→ indexar
```

Cada etapa es una cola en la tabla `tareas`:

- **Tomar trabajo:** los trabajadores toman tareas con
  `SELECT … FOR UPDATE SKIP LOCKED`, así que varios procesos pueden trabajar
  sin chocar.
- **Fallas:** una tarea que falla se reintenta con espera creciente. Si el
  error es permanente (por ejemplo, falta una llave), se marca fallida de
  inmediato.
- **Tareas largas:** mandan un latido; si un worker muere, sus tareas vuelven
  a la cola a los 15 minutos.
- **Sin duplicados:** extraer, fichar, ubicar e indexar llevan una clave.
- **Detener una corrida** cancela lo pendiente; lo que está en curso termina.
- **Cuántas a la vez:** `trabajadores` en `config/docubot.yaml`. El ritmo por
  dominio se coordina dentro de cada proceso de worker.

| etapa | entra | sale |
|---|---|---|
| descubrir | una fuente del perfil (o una consulta del buscador) | sitios por explorar y candidatos |
| explorar | un sitio | candidatos con puntaje |
| descargar | un candidato aceptado | un documento en el almacén (por sha256) |
| extraer | un documento | su texto |
| fichar | documento + perfil | la ficha |
| ubicar | documento + perfil | su lugar |
| indexar | un documento con texto | fragmentos con vectores |

## Datos

| tabla | qué guarda |
|---|---|
| `perfiles` | copia de cada YAML válido, con su huella |
| `corridas` | cada ejecución: copia del perfil, ajustes, estado |
| `sitios`, `corrida_sitios` | dominios explorados y su estado en cada corrida |
| `candidatos` | URLs encontradas por perfil: fuente, puntaje, estado, motivo |
| `documentos` | archivos descargados, uno por sha256 |
| `textos` | texto extraído, con su índice de texto completo |
| `fichas` | la ficha de cada documento por perfil, con estado, confianza y control |
| `fragmentos` | pedazos de texto con su vector |
| `lugares`, `catalogos` | catálogos geográficos (PostGIS) |
| `documento_lugares` | dónde aplica cada documento |
| `tareas` | la cola |

## Eventos en vivo

Las etapas publican eventos (`tarea`, `sitio`, `descarga`, `ficha`, `lugar`,
`corrida`) con `NOTIFY` dentro de su transacción: el aviso sale solo si los
datos se guardaron. La API escucha con una conexión `LISTEN` y los reparte por
WebSocket (`/api/eventos`). La interfaz refresca en lotes solo las consultas
afectadas. Un cliente lento pierde los avisos más viejos en lugar de frenar a
los demás.

## Código

```
backend/src/docubot/
  ajustes.py        config/docubot.yaml + variables DOCUBOT_*
  cli.py            comando docubot
  main.py           aplicación FastAPI
  api/              rutas HTTP y WebSocket
  db/               modelos (SQLAlchemy) y sesiones
  migraciones/      esquema versionado (Alembic)
  perfiles/         esquema del YAML, carga, mensajes de error, sincronización
  red/              cliente HTTP: robots.txt, ritmo, reintentos, TLS
  descubrimiento/   fuentes, buscadores, explorador, sitemaps, enlaces
  filtros/          dominios, tipos de documento, puntaje, referencia
  documentos/       almacén por huella, validación, texto de PDFs
  ia/               proveedores, fichas (prompt y validación), evaluación
  geo/              catálogos, búsqueda de lugares en el texto, ubicación
  busqueda/         fragmentos, vectores, búsqueda por palabras, tema o mixta
  pipeline/         cola, worker, corridas y etapas
  eventos.py        NOTIFY y difusión por WebSocket
frontend/src/
  api/              cliente tipado, consultas (TanStack Query), eventos
  componentes/      interfaz común: visor PDF, ficha, tablas, mapa...
  paginas/          una por pantalla
```

## Decisiones

- **Postgres hace de cola** en lugar de Redis o RabbitMQ: un servicio menos, y
  las tareas viven en la misma transacción que los datos que producen.
- **Los archivos se guardan por huella** (sha256), no por URL ni por número de
  fila: el mismo documento en dos sitios es uno solo, y nada depende del orden.
- **Los perfiles son archivos.** La base guarda la copia con la que se hizo
  cada corrida. El descubrimiento usa esa copia; las fichas, los lugares y la
  búsqueda usan el perfil actual.
- **La IA propone, la persona dispone:** cada ficha y cada lugar dudoso va a
  revisión con sus motivos, y lo elegido a mano no se pisa.
