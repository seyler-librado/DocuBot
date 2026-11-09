# Plan de DocuBot

Última actualización: 2026-11-09

## Qué es

DocuBot descubre, descarga y cataloga documentos publicados en la web según
**perfiles** configurables. Un perfil (YAML) dice qué buscar: en qué dominios,
con qué consultas a buscadores, qué documentos cuentan y qué campos llenar en
su ficha. El motor no sabe nada del tema: el mismo DocuBot sirve para planes
municipales, reglamentos, normas, presupuestos o cualquier colección de
documentos públicos.

Es un proyecto de código abierto (MIT), pensado para que cualquiera lo levante
con `docker compose up`.

### Por qué una versión nueva

La versión anterior funcionaba, pero la obtención de links estaba revuelta:

- **Las listas de entrada no se podían regenerar.** Dominios, candidatos de
  archivo y de portales estatales venían de otro proyecto, sin código que las
  volviera a crear.
- **Todo dependía del número de renglón de un CSV.** El nombre de cada PDF lo
  llevaba: no se podían borrar ni reordenar filas, y las descargas reanudaban
  saltándose huecos.
- **La web copiaba y parchaba el código del CLI**, en lugar de compartirlo.
- **Estaba atada a un solo tema y a un solo proveedor de IA.**

## Principios

1. **Configurable, no programado.** Lo que cambia entre temas va en YAML.
2. **Reanudable.** Cada etapa guarda su estado en Postgres; si algo se cae,
   sigue donde quedó.
3. **Un documento, una huella.** Los archivos se identifican por sha256; varias
   URLs pueden llevar al mismo documento.
4. **Buenos modales en la web.** User agent identificable, robots.txt
   (desactivable por perfil) y ritmo por dominio.
5. **La IA propone, la persona dispone.** Las fichas llevan confianza y motivos;
   lo dudoso va a revisión.
6. **Lugares por clave, nunca por nombre.** Los nombres se repiten (hay 88
   nombres de municipio que existen en más de un estado en México).

## Arquitectura

```
perfil.yaml → descubrir → explorar → filtrar → descargar → extraer → ficha IA → ubicar → indexar
                  └──────────────── PostgreSQL: cada etapa es una cola ────────────────┘
```

| servicio | tecnología | papel |
|---|---|---|
| `db` | Postgres 16 + PostGIS + pgvector | datos, cola de tareas, geografía, vectores |
| `migrar` | Alembic | aplica el esquema al arrancar |
| `api` | FastAPI | API REST + eventos en vivo |
| `worker` | asyncio | trabajadores del pipeline (N por etapa) |
| `web` | React + Vite + Tailwind, nginx | interfaz |
| `ollama` (opcional) | Ollama | IA local |
| `searxng` (opcional) | SearXNG | buscador propio, sin llave |
| `playwright` (opcional) | Chromium | sitios hechos en JavaScript |

### Configuración

| archivo | contenido |
|---|---|
| `config/docubot.yaml` | IA, trabajadores por etapa, red, almacén |
| `config/perfiles/*.yaml` o `*/perfil.yaml` | un perfil por colección |
| `.env` | contraseñas y llaves (no se versiona) |

Cualquier ajuste global se sobrescribe con `DOCUBOT_<SECCION>__<CAMPO>`.

### Modelo de datos

| tabla | qué guarda |
|---|---|
| `perfiles` | copia de cada YAML válido, con su huella |
| `corridas` | cada ejecución del pipeline para un perfil |
| `sitios` | dominios explorados, su estado y su lugar |
| `candidatos` | URLs encontradas (por perfil), de dónde salieron, tipo, puntaje |
| `documentos` | archivos descargados, por sha256 |
| `textos` | texto extraído |
| `fichas` | campos del perfil para cada documento, con estado y confianza |
| `lugares` | catálogo geográfico (clave, nombre, alias, nivel, padre, geometría) |
| `documento_lugares` | dónde aplica cada documento (o candidatos si es ambiguo) |
| `tareas` | la cola del pipeline |

## Fases

Leyenda: ✅ hecha · 🔜 siguiente · ⏳ pendiente

Al terminar cada fase: pruebas en verde, README al día y un commit.

### ✅ Fase 0. Esqueleto

- `docker compose` con base de datos, migraciones, API, worker y web.
- Esquema inicial de todas las tablas, con Alembic.
- Cola de tareas en Postgres (`FOR UPDATE SKIP LOCKED`), reintentos con espera
  creciente y recuperación de tareas huérfanas.
- Ajustes en YAML sobrescribibles por variables de entorno.
- Pantalla de estado del sistema.
- Pruebas con su propia base: `docker compose --profile pruebas run --rm pruebas`.

### ✅ Fase 1. Perfiles y red

- **Esquema completo del perfil:**
  - dominios permitidos y bloqueados;
  - fuentes: semillas, lista de dominios, buscador con variables, Common Crawl, Wayback;
  - exploración y tipos de documento;
  - campos de ficha, geografía, referencia y red.
- **Validación con mensajes en español:** ruta exacta del error, "¿quisiste decir…?",
  revisión de archivos, de columnas de los CSV y de variables usadas en las consultas.
- **Perfiles** en archivo o en carpeta, sincronizados con la base al arrancar.
- **Cliente HTTP:**
  - robots.txt por origen, también en redirecciones, y desactivable;
  - ritmo y Crawl-delay por dominio;
  - reintentos con `Retry-After`;
  - respaldo para certificados TLS inválidos;
  - límite de tamaño y contenido comprimido.
- **Utilidades:** clave de URL para deduplicar y filtro de dominios.
- **CLI:** `docubot perfiles listar|validar|sincronizar`, `docubot red probar <url>`.

### ✅ Fase 2. Descubrimiento

- **Corridas:** se crean desde un perfil (guardan una copia de él), se detienen
  y se reanudan, y se cierran solas cuando ya no quedan tareas. Para lanzarlas:
  `docubot correr`, `docubot corridas listar|detener|reanudar`, la API
  `/api/corridas` y el botón **Correr** en la pantalla.
- **Fuentes** con la misma interfaz:
  - `semillas` y `lista_dominios` (con lugar por fila);
  - `buscador`: SearXNG, Brave, Serper y SerpAPI. Se reparte en una tarea por
    consulta y cada resultado hereda el lugar de su fila;
  - `commoncrawl`: índice CDX, paginado;
  - `wayback`: CDX del Internet Archive.
- **Explorador de sitios:**
  - portada con y sin www, http y https;
  - sitemaps, los declarados en robots.txt y /sitemap.xml;
  - recorrido por prioridad (semillas, secciones, tipos de documento), con
    profundidad, máximo de páginas y de tiempo;
  - enlaces en `a`, `area`, `iframe`, `embed` y `object`;
  - documentos por extensión, HEAD o GET;
  - visores de Drive, Dropbox y OneDrive convertidos a descarga directa;
  - descarte de redes sociales y dominios estacionados.
- **Deduplicación en la base:** un sitio se explora una vez por corrida (tabla
  `corrida_sitios`) y cada candidato se guarda una vez por perfil y URL
  normalizada.
- **Ajustes de red por perfil** (`red.respetar_robots`, ritmo), con clientes
  HTTP compartidos por proceso para que el ritmo por dominio se respete entre tareas.
- **Worker:**
  - latido para tareas largas;
  - errores permanentes (como una llave faltante) que no se reintentan;
  - cancelación al detener una corrida.
- **SearXNG** como servicio opcional (`--profile searxng`).
- **Pruebas:** sitio simulado completo, buscadores y CDX simulados, corridas de
  punta a punta (62 pruebas en total).
- **Probado en real:** una corrida del perfil de ejemplo exploró sitios
  municipales y encontró reglamentos de tránsito en varios municipios.

Pendiente, para otra fase: `exploracion.javascript` (sitios hechos en JavaScript,
con Playwright). Por ahora se avisa en la bitácora y se explora sin navegador.

### ✅ Fase 3. Filtros y descarga

- **Puntaje de cada candidato** al encontrarse:
  - el tipo en el nombre del archivo (85), en el texto del enlace (80) o solo
    en la ruta (50);
  - +10 si trae año, −15 si el nombre no dice nada, 0 si tiene una palabra
    excluida, 70 en `modo: todos`;
  - con eso queda aceptado o rechazado, con su motivo; si un candidato
    reaparece con mejor puntaje, se acepta.
- **Descarga de los aceptados** conforme aparecen, primero los de mayor
  puntaje, sin encolar dos veces el mismo. Se puede apagar por corrida
  (`--sin-descargar`) y lanzar después (`docubot descargar <corrida>`).
- **Almacén por sha256** (`almacen/ab/cd/<sha256>.<ext>`), escritura en
  temporal y movimiento atómico; el mismo contenido de varias URLs es un solo
  documento.
- **Validación:** HTML disfrazado, PDF incompleto (sin `%%EOF`), vacío y
  formatos de oficina.
- **Errores:**
  - pasajeros (5xx, 429, sin conexión): se reintentan con espera;
  - definitivos (404, dominio inexistente, HTML, incompleto, demasiado grande,
    robots.txt): pasan al respaldo del Internet Archive y, si tampoco sirve,
    el candidato queda `fallido` con su motivo.
- **Dominios que no resuelven DNS:** fallan de inmediato, sin reintentos
  (también acelera la exploración de dominios muertos).
- **Referencia:** marca `nuevo` según url, tipo, lugar o sha256.
- **Recalificar** los candidatos de un perfil tras cambiar sus tipos.
- **API:** `/api/documentos`, `/api/documentos/{id}/archivo`,
  `/api/corridas/{id}/descargar` y filtros por estado.
- **Pantalla:** aceptados, descargados y MB por corrida.
- **Pruebas:** 73 en total.
- **Probado en real:** 54,184 candidatos de la corrida de ejemplo →
  1,859 aceptados (3.4 %); se bajaron los 15 mejores (61 MB), uno de ellos
  desde el Internet Archive porque su dominio ya no existe.

### ✅ Fase 4. Texto, IA y fichas

- **Etapa `extraer`:**
  - texto de todas las páginas (pypdf, con pypdfium2 de respaldo), con un tope;
  - detecta documentos escaneados e ilegibles y dice por qué;
  - corre en un hilo aparte para no frenar a las demás tareas.
- **Etapa `fichar`:**
  - el prompt se arma con los campos del perfil;
  - clasificación a ciegas (no se le dice qué tipo se espera);
  - páginas escaneadas como imagen si el modelo tiene visión;
  - si no cabe, recorta el texto y reintenta.
- **Validación de la ficha:**
  - JSON aunque venga con prosa;
  - fechas normalizadas, opciones cerradas (con tolerancia a erratas), listas y números;
  - corrección de erratas y acentos contra el texto del documento;
  - detección de respuestas que hablan de otro documento;
  - estado (ok/revision/ilegible/error), confianza (alta/media/baja), motivos y
    datos de control (método, segundos, tokens, tipo según la IA).
- **Proveedores intercambiables:** `ollama` (servicio opcional en Docker,
  con GPU comentada), `openai`, `openai_compat` y `anthropic`, con reintentos
  ante fallas pasajeras y errores permanentes que no se reintentan.
- **Extensiones propias** (`config/extensiones/archivo.py:Clase`, no se
  versionan). Así se conectó un servidor de IA propio: su dirección y su llave viven solo en `.env`.
- **Pipeline:** descargar → extraer → fichar, sin encolar dos veces la misma
  tarea; una ficha por documento y perfil.
- **Comandos y API:**
  - CLI: `docubot ia probar`, `docubot fichas <corrida> [--rehacer]`;
  - API: `/api/ia/salud`, `/api/ia/probar`, `/api/documentos/{id}` (texto,
    fichas, fuentes), `/api/corridas/{id}/fichas`.
- **Pruebas:** 92 en total, con PDFs reales generados en la prueba y una IA simulada.
- **Probado en real con un servidor de IA remoto:** 15 reglamentos, ~5 s por ficha:
  - 13 quedaron ok con confianza alta;
  - 2 quedaron en revisión, con razón: eran ejemplares completos del Periódico
    Oficial que traen reglamentos adentro.

Pendiente:
- **Conjunto dorado** de documentos con su ficha correcta para medir el
  acierto de cada modelo (fase 8, con los ejemplos).
- **Probar Ollama** en una máquina con recursos.

### ✅ Fase 5. Interfaz

- **Eventos en vivo:**
  - el worker publica con NOTIFY de Postgres: tarea, sitio, descarga, ficha y corrida;
  - la API los reparte por WebSocket (`/api/eventos`), con latido y sin que un
    cliente lento frene a los demás;
  - la interfaz refresca en lotes solo lo afectado.
- **Pantallas:**

  | pantalla | qué hace |
  |---|---|
  | Panel | cifras, corridas recientes, últimos documentos y actividad |
  | Perfiles y su detalle | con su YAML y diálogo para correrlos con ajustes de una sola corrida: fuentes, descarga, robots.txt, profundidad, páginas, ritmo y puntaje mínimo |
  | Corridas y su detalle en vivo | línea del pipeline por etapa, cifras, sitios, candidatos, documentos, fallas y actividad; detener, reanudar, bajar aceptados, fichas faltantes |
  | Biblioteca | portadas, filtros por perfil, tipo, estado de ficha y búsqueda, en la URL |
  | Documento | visor PDF (pdf.js: páginas, zoom, teclado) junto a la ficha editable según el tipo de cada campo, aprobar, rehacer con IA, fuentes, texto extraído |
  | Revisión | por revisar, con error, ilegibles; aprobar rápido |
  | Candidatos | puntaje, filtros, aceptar o rechazar a mano (aceptar encola la descarga) |
  | Ajustes | configuración actual y prueba de la IA |

- **Tema** claro, oscuro o del sistema, sin parpadeo. Diseño adaptable al celular.
- **API nueva:**
  - `/api/resumen` y `/api/fichas`;
  - `/api/candidatos` (con PATCH);
  - biblioteca paginada con filtros, `/api/documentos/{id}/portada` (en caché
    por huella) y edición, aprobación y rehecho de fichas;
  - `/api/corridas/{id}/fallas`, `/api/perfiles/{nombre}/yaml` y ajustes por corrida.
- **Cambio respecto al plan:** en lugar de shadcn/ui y un cliente generado desde
  OpenAPI, componentes propios ligeros con Tailwind y un cliente tipado escrito
  a mano (`frontend/src/api/cliente.ts`). Es menos maquinaria para el mismo
  resultado; se puede generar más adelante si la API crece.
- **Verificado en navegador** (Edge sin ventana): panel, corrida, documento con
  el PDF dibujado, revisión y celular. Se corrigió que nginx servía el worker
  de pdf.js (`.mjs`) con un tipo que los navegadores rechazan.
- **Pruebas:** 98 en total (API de la interfaz y eventos incluidos).

### ✅ Fase 6. Geografía y mapa

- **Catálogo de México** (`config/catalogos/mexico`), con datos de INEGI:
  32 estados y 2,475 municipios, con claves INEGI, polígonos simplificados,
  coordenadas de la cabecera y alias. Los alias son la cabecera cuando se
  llama distinto (Benito Juárez → Cancún), la forma corta (Tulancingo de
  Bravo → Tulancingo) y nombres comunes de estados. El Estado de México se
  llama así completo para que «México» no lo active.
- **Importación de catálogos** (CSV + GeoJSON) a PostGIS, idempotente por
  huella. Se hace al arrancar la API, al crear una corrida o con
  `docubot lugares importar`.
- **Etapa `ubicar`**, después de la ficha (o de la extracción si no hay IA):
  - capa de fuente: clave de la fila;
  - capa de contenido: título, campo `lugar` de la IA y texto;
  - búsqueda de nombres por coincidencia más larga, con peso por contexto;
  - el estado mencionado en otra parte desempata;
  - tope de menciones y media voz para palabras sueltas;
  - el estado protagonista gana al municipio nombrado de pasada;
  - empates de nombres iguales: «ambiguo»; fuente y texto en conflicto:
    «revision»; sin lugar: «sin_lugar»;
  - lo elegido a mano no se pisa.
- **Las fichas y lugares siguen el perfil actual**, no la copia guardada en la
  corrida: si cambias campos o agregas un catálogo, se aplica a lo ya descargado.
- **API:**
  - `/api/mapa`: conteos por lugar;
  - `/api/mapa/poligonos`: GeoJSON simplificado, en caché;
  - `/api/mapa/niveles`, `/api/catalogos` y `/api/lugares/buscar`;
  - `PUT /api/documentos/{id}/lugar` y `/api/lugares/dudosos`;
  - `/api/corridas/{id}/lugares`;
  - filtro `lugar` en la biblioteca (incluye lo que contiene).
- **Interfaz:**
  - página Mapa (MapLibre sobre OpenStreetMap, configurable): municipios
    sombreados por número de documentos, estados con documentos estatales,
    puntos y panel con los documentos del lugar;
  - «Dónde aplica» en cada documento, con candidatos y buscador para corregir;
  - pestaña «Lugares por decidir» en Revisión;
  - etapa Ubicar en la línea del pipeline.
- **Pruebas:** 102 en total, entre ellas los casos de desambiguación (Benito
  Juárez, Hidalgo estado/municipio, Puebla, «Reforma»).
- **Probado en real** con los 15 reglamentos, todos bien ubicados:
  - Benito Juárez en Quintana Roo y La Paz en el Estado de México, ambos
    nombres que se repiten en otros estados;
  - Monterrey, Cuautitlán y Tlajomulco;
  - los del Congreso de Durango, en el estado.

  La primera versión cayó en «Nombre de Dios», «Reforma» y «Tulum». De ahí
  salieron las reglas de palabra común y de estado protagonista.

### ✅ Fase 7. Búsqueda

- **Texto completo en Postgres** con la configuración `docubot_es`: español,
  sin acentos y por raíz.
  - Columnas calculadas e índices GIN en `textos` (hasta 400 mil caracteres
    por documento) y en `fichas` (el título pesa A, el resto de la ficha B).
  - Las consultas normales piden algunas palabras, no todas, y las que tienen
    todas puntúan más. Con comillas, `-` u `OR` se respeta la sintaxis de buscador.
  - Pasajes con `ts_headline`, con la página de la primera palabra resaltada.
- **Búsqueda por tema:**
  - fragmentos de ~900 caracteres por página, con solape, y vectores en
    pgvector (tabla `fragmentos`);
  - modelo local en CPU (fastembed: `paraphrase-multilingual-MiniLM-L12-v2`,
    384 dimensiones, unos 100 fragmentos por segundo) o `/v1/embeddings` de
    Ollama, OpenAI o un servidor compatible;
  - umbral de similitud y ventana respecto al mejor resultado, para no
    devolver «todo».
- **Mixta:** Reciprocal Rank Fusion de las dos listas.
- **Etapa `indexar`**, después de extraer el texto (independiente de la IA).
  Comandos: `docubot busqueda indexar|buscar`.
- **API:** `/api/buscar` (con los mismos filtros que la biblioteca),
  `/api/busqueda/estado` y `/api/busqueda/indexar`.
- **Interfaz:**
  - página Buscar con modos, filtros y pasajes resaltados que abren el PDF en
    su página;
  - buscador en el Panel y atajo `/` desde cualquier pantalla;
  - estado del índice en Ajustes y etapa Indexar en la línea del pipeline.
- **Pruebas:** 109 en total.
- **Probado en real** con los 15 reglamentos (3,236 fragmentos):
  - «sanciones por estacionarse en lugar prohibido» encuentra el artículo y su página;
  - «multas de tránsito» trae los tres reglamentos de tránsito en su artículo de multas;
  - «cuidado del medio ambiente y árboles» encuentra el reglamento ambiental
    aunque no dice «árboles»;
  - «receta de cocina» no trae nada por tema.

Límite conocido: en un acervo muy homogéneo (puros reglamentos), las consultas
genéricas («reglas para…») se parecen a casi todo por tema; el orden sigue
siendo útil y la búsqueda mixta lo compensa.

### ✅ Fase 8. Ejemplos, documentación y preparación para publicar

- **`ejemplos/`** con tres perfiles listos para copiar, validados por una prueba:
  - `planeacion-municipal-mx`: 2,475 municipios con clave INEGI y 1,642
    dominios conocidos, 8 tipos de documento (adaptados de la versión
    anterior), ficha con lugar y catálogo de México;
  - `normas-oficiales-mx`: NOM y NMX, por buscador y Common Crawl;
  - `ordenanzas-municipales-es`: España, otro dominio y sin catálogo.
- **Medir a la IA:** `docubot ia evaluar` compara las fichas contra un conjunto
  dorado (`dorado.csv` + PDFs) y da los aciertos por campo. Los conjuntos van
  en `config/evaluacion/`, que no se versiona.
- **Documentación** en `docs/`:
  - guías: perfiles, descubrimiento, IA, geografía, búsqueda, configuración,
    comandos y API, arquitectura y preguntas frecuentes;
  - README para GitHub con capturas;
  - guía para publicar (`docs/PUBLICAR.md`).
- **Calidad:**
  - CI en GitHub Actions: pruebas con Postgres real, ruff, compilación de la
    interfaz e imágenes de Docker;
  - ruff configurado y todo el backend formateado;
  - Dependabot;
  - plantillas de issues y PR, `CONTRIBUTING.md`, `SECURITY.md` y `CHANGELOG.md`.
- **Auditoría:** nada privado en lo versionado ni en el historial.
- **Pruebas:** 117 en total.
- **Descartado: el importador de datos de la versión anterior.** El sistema
  nuevo los vuelve a descubrir solo, y esos datos eran de un uso
  institucional que no va en un proyecto público.
- **Pendiente:** publicar (ver `docs/PUBLICAR.md`), cuando se decida nombre,
  licencia y cuenta.

## Decisiones pendientes

| tema | opciones | cuándo |
|---|---|---|
| Buscador de pago | Brave o Serper (requieren llave); SearXNG no | fase 2 |
| Modelo local | depende del equipo (RAM/GPU); por ahora un servidor remoto | cuando haya equipo |
| Nombre del repositorio | "DocuBot" u otro | al publicar |
| Licencia | MIT por ahora | al publicar |

## Riesgos conocidos

- **Redes que bloquean apt.** En algunas redes corporativas, la construcción de
  la imagen de la base se cuelga al descargar paquetes. Se resuelve con
  `APT_USER_AGENT` en `.env`.
- **Sitios lentos o caídos.** Los servidores públicos se saturan rápido; el
  ritmo por dominio es conservador a propósito.
- **Sitios hechos en JavaScript.** Sin el servicio de navegador no muestran
  sus enlaces; queda como opción del perfil (`exploracion.javascript`).
- **Sitios fuera del dominio esperado.** Muchos municipios no usan `.gob.mx`;
  por eso las listas de dominios y los buscadores pueden permitir otros
  dominios.
- **Ignorar robots.txt.** Es posible, pero debe usarse con criterio; el ritmo
  por dominio se respeta siempre.
