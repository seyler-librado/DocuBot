# Configuración: referencia

| dónde | qué va |
|---|---|
| `config/docubot.yaml` | ajustes globales (IA, trabajadores, red, buscadores, búsqueda, mapa, almacén) |
| `config/perfiles/` | un perfil por colección (ver [perfiles](perfiles.md)) |
| `config/extensiones/` | proveedores de IA propios (ver su README) |
| `config/catalogos/` | catálogos de lugares |
| `.env` | contraseñas, llaves y puertos; nunca se versiona (parte de `.env.example`) |

Los cambios se aplican al reiniciar: `docker compose up -d`.

## Prioridad y variables de entorno

De mayor a menor: variables de entorno, `.env`, `config/docubot.yaml` y los
valores por omisión.

Cualquier ajuste se sobrescribe con `DOCUBOT_<SECCION>__<CAMPO>` (doble guion
bajo entre sección y campo):

```bash
DOCUBOT_TRABAJADORES__DESCARGA=8
DOCUBOT_IA__PROVEEDOR=ollama
DOCUBOT_BUSQUEDA__EMBEDDINGS=ninguno
```

## `ia`: fichas con IA

| campo | omisión | qué hace |
|---|---|---|
| `proveedor` | `ninguno` | `ninguno` (sin fichas), `ollama`, `openai`, `openai_compat`, `anthropic` o una extensión `archivo.py:Clase` en `config/extensiones/` |
| `modelo` | `""` | modelo del proveedor (obligatorio salvo en extensiones que no lo pidan) |
| `url` | `""` | raíz `/v1` del servidor; `ollama` usa `http://ollama:11434/v1`, `openai` usa `https://api.openai.com/v1`, `anthropic` usa `https://api.anthropic.com/v1`; `openai_compat` la necesita |
| `llave` | — | va en `.env`: `DOCUBOT_IA__LLAVE` |
| `temperatura` | `0` | 0 a 2 |
| `max_tokens_salida` | `1500` | 100 a 32000 |
| `timeout` | `180` | segundos por respuesta |
| `reintentos` | `2` | ante fallas pasajeras, antes de devolver la tarea a la cola (0 a 10) |
| `vision` | `true` | leer por imagen los documentos escaneados, si el modelo puede |
| `paginas` | `12` | páginas de texto que se le dan (1 a 200) |
| `paginas_imagen` | `3` | páginas escaneadas que se le mandan como imagen (1 a 20) |
| `max_caracteres` | `16000` | tope del texto que se le da (≥ 1000) |

## `trabajadores`: tareas a la vez por etapa

| campo | omisión | etapas |
|---|---|---|
| `descubrimiento` | `2` | descubrir (fuentes) |
| `exploracion` | `4` | explorar (sitios) |
| `descarga` | `4` | descargar |
| `extraccion` | `2` | extraer texto, ubicar, indexar |
| `ia` | `1` | fichar |

Rango 0 a 64 (`ia`: 0 a 16). Son del proceso `worker`: se cambian aquí, no por
corrida.

## `red`

| campo | omisión | qué hace |
|---|---|---|
| `user_agent` | `DocuBot/0.1 (+https://github.com/seyler-librado/DocuBot)` | cómo se identifica; pon una URL o correo de contacto. Su primera palabra es el nombre que se busca en robots.txt |
| `peticiones_por_segundo_por_dominio` | `1.0` | ritmo por dominio (> 0) |
| `simultaneas_por_dominio` | `2` | peticiones a la vez a un mismo dominio (1 a 16) |
| `respetar_robots` | `true` | `false` ignora robots.txt (también por perfil) |
| `timeout` | `30` | segundos por petición |
| `reintentos` | `3` | ante errores de conexión, 429 y 5xx, con espera creciente o la de `Retry-After` (0 a 10) |
| `max_redirecciones` | `10` | 0 a 30 |
| `max_mb_pagina` | `10` | tamaño máximo de una página HTML |
| `verificar_tls` | `true` | verificar certificados |
| `reintentar_sin_tls` | `true` | si un certificado está mal, reintentar sin verificar (se anota el sitio) |

Un dominio que no resuelve DNS falla de inmediato, sin reintentos.

## `buscadores`

| campo | omisión | qué hace |
|---|---|---|
| `searxng_url` | `http://searxng:8080` | SearXNG (`docker compose --profile searxng up -d`) |
| `brave_llave` | — | `.env`: `DOCUBOT_BUSCADORES__BRAVE_LLAVE` |
| `serper_llave` | — | `.env`: `DOCUBOT_BUSCADORES__SERPER_LLAVE` |
| `serpapi_llave` | — | `.env`: `DOCUBOT_BUSCADORES__SERPAPI_LLAVE` |
| `pais` | `""` | país preferido para los resultados (p. ej. `mx`) |
| `idioma` | `es` | idioma preferido |

Si falta la llave de un motor, la tarea falla de inmediato con un mensaje que
dice qué variable definir.

## `busqueda`

El texto completo siempre está activo; esto configura la búsqueda por tema.

| campo | omisión (código) | qué hace |
|---|---|---|
| `embeddings` | `ninguno` | `ninguno`, `local` (modelo en CPU dentro del contenedor), `ollama`, `openai`, `openai_compat`. El `config/docubot.yaml` incluido usa `local` |
| `modelo` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | con `local`, un modelo de fastembed; con los demás, el del servidor |
| `url` | `""` | raíz `/v1` (necesaria con `openai_compat`; `ollama` y `openai` tienen la suya) |
| `llave` | — | `.env`: `DOCUBOT_BUSQUEDA__LLAVE` |
| `tamano_fragmento` | `900` | caracteres por fragmento (200 a 8000) |
| `solape` | `150` | caracteres que se enciman entre fragmentos (0 a 2000) |
| `max_fragmentos` | `400` | fragmentos por documento, desde las primeras páginas |
| `similitud_minima` | `0.45` | parecido mínimo (0 a 1) para que un documento entre por tema |
| `ventana_similitud` | `0.2` | además, no más lejos que esto del mejor resultado |
| `carpeta_modelos` | `/datos/modelos` | dónde se guarda el modelo local (volumen `modelos`) |

Si cambias de modelo, reindexa: `docubot busqueda indexar --rehacer`.

## `mapa`

| campo | omisión | qué hace |
|---|---|---|
| `teselas` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | mapa base |
| `atribucion` | `© OpenStreetMap` | atribución que exige el mapa base |

Los polígonos del catálogo se dibujan encima, así que el mapa funciona aun sin
mapa base.

## `almacen`

| campo | omisión | qué hace |
|---|---|---|
| `carpeta` | `/datos/almacen` | dónde se guardan los documentos (`./almacen` en la máquina) |
| `tamano_max_mb` | `200` | tope por documento (un perfil puede poner el suyo) |
| `respaldo_wayback` | `true` | si un documento ya no está, intentar la copia del Internet Archive |

## Otros ajustes

Normalmente los pone `docker-compose.yml`.

| variable | qué hace |
|---|---|
| `DOCUBOT_BASE_DATOS_URL` | conexión a Postgres |
| `DOCUBOT_CONFIG` | ruta de `docubot.yaml` |
| `DOCUBOT_CARPETA_PERFILES` | carpeta de perfiles |
| `DOCUBOT_CARPETA_EXTENSIONES` | carpeta de extensiones |

## `.env`

| variable | omisión | qué hace |
|---|---|---|
| `POSTGRES_PASSWORD` | `docubot` | contraseña de Postgres (cámbiala) |
| `WEB_PUERTO` | `8080` | puerto de la interfaz (solo en 127.0.0.1) |
| `DB_PUERTO` | `5433` | puerto de Postgres para conectarse con un cliente (solo en 127.0.0.1) |
| `SEARXNG_PUERTO` | `8888` | puerto de SearXNG para probarlo a mano |
| `SEARXNG_SECRET` | `cambia-esto` | clave interna de SearXNG |
| `TZ` | `UTC` | zona horaria de los contenedores |
| `APT_USER_AGENT` | — | solo si la imagen de la base se cuelga descargando paquetes: algunas redes bloquean el user agent de apt (p. ej. `Mozilla/5.0`) |
| `DOCUBOT_IA__LLAVE`, `DOCUBOT_BUSCADORES__*_LLAVE`, `DOCUBOT_BUSQUEDA__LLAVE` | — | llaves |

## Servicios de Docker

| servicio | perfil de compose | qué es |
|---|---|---|
| `db` | — | Postgres 16 con PostGIS y pgvector |
| `migrar` | — | aplica las migraciones y termina |
| `api` | — | API y eventos en vivo |
| `worker` | — | trabajadores del pipeline |
| `web` | — | interfaz (nginx) en `127.0.0.1:${WEB_PUERTO}` |
| `searxng` | `searxng` | buscador propio, sin llaves |
| `ollama` | `ollama` | IA local (con GPU NVIDIA, quita los comentarios de `deploy:`) |
| `pruebas` | `pruebas` | corre las pruebas con su propia base |

```bash
docker compose --profile searxng up -d
docker compose --profile ollama up -d
docker compose --profile pruebas run --rm --build pruebas
```

| volumen o carpeta | contenido |
|---|---|
| `pgdata` | la base de datos |
| `modelos` | el modelo local de búsqueda por tema |
| `ollama` | los modelos de Ollama |
| `./almacen` | los documentos descargados y sus portadas |
| `./config` | se monta en solo lectura |
