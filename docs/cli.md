# Línea de comandos y API

Todo lo que hace la interfaz también se puede hacer desde la terminal:

```bash
docker compose exec api docubot --help
docker compose exec api docubot <comando> --help
```

## Comandos

### Servicios

Los usa `docker-compose.yml`; normalmente no hace falta llamarlos a mano.

| comando | qué hace |
|---|---|
| `docubot api [--host 127.0.0.1] [--puerto 8000] [--recargar]` | levanta la API |
| `docubot worker` | levanta los trabajadores del pipeline |
| `docubot migrar [--revision head]` | aplica las migraciones de la base |
| `docubot eco [MENSAJE] [--veces 1]` | encola tareas de prueba para ver que el worker responde |

```bash
docker compose exec api docubot eco "hola" --veces 3
docker compose logs -f worker
```

### Perfiles

| comando | qué hace |
|---|---|
| `docubot perfiles listar` | perfiles encontrados y si son válidos |
| `docubot perfiles validar [RUTAS...]` | valida y explica cada error; sale con código 1 si alguno falla |
| `docubot perfiles sincronizar` | copia los perfiles válidos a la base |

```bash
docker compose exec api docubot perfiles validar
docker compose exec api docubot perfiles validar config/perfiles/mi-perfil.yaml
```

### Corridas

| comando | qué hace |
|---|---|
| `docubot correr PERFIL [-f N ...] [--no-esperar] [--sin-descargar]` | lanza una corrida. `-f/--fuente` limita a esas fuentes (índices desde 0); `--no-esperar` no muestra el avance; `--sin-descargar` solo descubre y califica |
| `docubot corridas listar [--limite 10]` | las corridas más recientes |
| `docubot corridas detener ID` | cancela lo pendiente (lo que está en curso termina) |
| `docubot corridas reanudar ID [--fallidas]` | retoma una corrida detenida; con `--fallidas` reintenta también lo que falló |
| `docubot descargar ID [--limite N] [--fallidos]` | encola la descarga de los aceptados que falten (los N de mayor puntaje); `--fallidos` reintenta los que fallaron |
| `docubot fichas ID [--rehacer]` | encola extracción de texto, fichas y ubicación de lo descargado; `--rehacer` rehace las fichas existentes |
| `docubot candidatos recalificar PERFIL` | recalcula los puntajes con el YAML actual |

```bash
docker compose exec api docubot correr reglamentos-municipales -f 1 --sin-descargar
docker compose exec api docubot descargar 3 --limite 50
```

### IA

| comando | qué hace |
|---|---|
| `docubot ia probar` | muestra el proveedor y le hace una pregunta de ida y vuelta |
| `docubot ia evaluar CARPETA --perfil PERFIL [--salida informe.json]` | mide los aciertos de la IA contra un conjunto dorado (PDFs + `dorado.csv`; ver `backend/src/docubot/ia/evaluar.py`) |

```bash
docker compose exec api docubot ia probar
docker compose exec api docubot ia evaluar /app/config/evaluacion/planes --perfil planeacion-municipal-mx
```

### Lugares

| comando | qué hace |
|---|---|
| `docubot lugares importar PERFIL [--forzar]` | importa el catálogo de lugares del perfil (si no cambió, no hace nada salvo con `--forzar`) |
| `docubot lugares ubicar ID` | vuelve a ubicar los documentos de una corrida (respeta lo elegido a mano) |

```bash
docker compose exec api docubot lugares ubicar 3
```

### Búsqueda

| comando | qué hace |
|---|---|
| `docubot busqueda indexar [--rehacer]` | encola los vectores de los documentos que no los tengan (o de todos) |
| `docubot busqueda buscar CONSULTA [--modo mixta\|palabras\|tema] [--limite 10]` | busca y muestra pasajes con su página |

```bash
docker compose exec api docubot busqueda buscar "multas de tránsito" --modo palabras
```

### Red

| comando | qué hace |
|---|---|
| `docubot red probar URL` | pide una URL como lo haría DocuBot (robots.txt, ritmo, reintentos, TLS) |

```bash
docker compose exec api docubot red probar https://www.gob.mx/
```

## API

La documentación interactiva está en <http://127.0.0.1:8080/api/docs>.

| método | ruta | qué hace |
|---|---|---|
| GET | `/api/salud` | estado de la base, extensiones y migración |
| GET | `/api/ajustes` | configuración actual (sin llaves) |
| GET | `/api/resumen` | cifras generales |
| GET | `/api/tareas/resumen` | tareas por etapa y estado |
| GET | `/api/perfiles` | perfiles con sus errores de validación |
| GET | `/api/perfiles/{nombre}` | detalle y configuración |
| GET | `/api/perfiles/{nombre}/yaml` | el YAML tal cual |
| POST | `/api/perfiles/sincronizar` | copia los perfiles válidos a la base |
| POST | `/api/corridas` | lanza una corrida: `{perfil, fuentes?, descargar?, ajustes?}` |
| GET | `/api/corridas` | corridas recientes con su avance |
| GET | `/api/corridas/{id}` | avance de una corrida |
| POST | `/api/corridas/{id}/detener` | detiene |
| POST | `/api/corridas/{id}/reanudar` | reanuda (`?reintentar_fallidas=true`) |
| POST | `/api/corridas/{id}/descargar` | encola descargas pendientes (`?limite=`, `?fallidos=`) |
| POST | `/api/corridas/{id}/fichas` | encola texto, fichas y ubicación (`?rehacer=`) |
| POST | `/api/corridas/{id}/lugares` | vuelve a ubicar sus documentos |
| GET | `/api/corridas/{id}/sitios` | sitios explorados |
| GET | `/api/corridas/{id}/candidatos` | candidatos de la corrida |
| GET | `/api/corridas/{id}/fallas` | tareas que fallaron, con su error |
| GET | `/api/candidatos` | todos los candidatos, con filtros |
| PATCH | `/api/candidatos/{id}` | aceptar (y encolar su descarga) o rechazar a mano |
| GET | `/api/documentos` | biblioteca con filtros (perfil, corrida, tipo, ficha, texto, lugar) |
| GET | `/api/documentos/{id}` | detalle: texto, fichas, lugares, fuentes |
| GET | `/api/documentos/{id}/archivo` | el archivo |
| GET | `/api/documentos/{id}/portada` | la primera página como imagen |
| PUT | `/api/documentos/{id}/fichas/{perfil}` | guarda una ficha corregida a mano |
| POST | `/api/documentos/{id}/fichas/{perfil}/aprobar` | aprueba una ficha |
| POST | `/api/documentos/{id}/fichas/{perfil}/rehacer` | pide a la IA rehacerla |
| PUT | `/api/documentos/{id}/lugar` | asigna el lugar a mano |
| GET | `/api/fichas` | cola de revisión (`?estado=revision`) |
| GET | `/api/ia/salud` | estado del proveedor de IA |
| POST | `/api/ia/probar` | pregunta de ida y vuelta |
| GET | `/api/catalogos` | catálogos de lugares importados |
| GET | `/api/mapa` | documentos por lugar para un perfil |
| GET | `/api/mapa/poligonos` | polígonos simplificados (GeoJSON) |
| GET | `/api/mapa/niveles` | niveles de un catálogo |
| GET | `/api/lugares/buscar` | busca lugares por nombre |
| GET | `/api/lugares/dudosos` | documentos con lugar ambiguo o en conflicto |
| GET | `/api/buscar` | búsqueda por palabras, tema o mixta, con pasajes |
| GET | `/api/busqueda/estado` | estado del índice |
| POST | `/api/busqueda/indexar` | encola los vectores que falten |
| WebSocket | `/api/eventos` | eventos en vivo (tarea, sitio, descarga, ficha, lugar, corrida) |
