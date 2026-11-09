# Perfiles: referencia

Un perfil es un archivo YAML que dice **qué buscar**: en qué dominios, con qué
fuentes, qué documentos cuentan y qué campos llenar en su ficha. El motor no
sabe nada del tema; todo lo específico va aquí.

Un campo desconocido es un error, así que una errata (`fuentess`) no pasa
desapercibida. Para revisar un perfil:

```bash
docker compose exec api docubot perfiles validar
```

Cada error dice dónde está y, si parece una errata, sugiere el nombre correcto.

## Dónde va

| forma | archivos que usa |
|---|---|
| `config/perfiles/<nombre>.yaml` | junto al YAML, en `config/perfiles/` |
| `config/perfiles/<nombre>/perfil.yaml` | dentro de su carpeta |

- Los archivos que empiezan con `_` o `.` se ignoran: sirven como borradores.
- Las rutas de archivos (CSV de variables, catálogo, referencia) son relativas
  a la carpeta del perfil.
- Dos perfiles no pueden tener el mismo `nombre`.
- Los perfiles propios no se versionan; solo `ejemplo.yaml`. Hay más ejemplos
  en [`ejemplos/`](../ejemplos).

## Estructura

```yaml
nombre: ...            # obligatorio
descripcion: ...
descubrimiento: {...}  # obligatorio: dónde buscar
documentos: {...}      # obligatorio: qué documentos cuentan
fichas: {...}          # qué campos llenar
geografia: {...}       # catálogo de lugares (opcional)
referencia: {...}      # lo que ya se tiene (opcional)
red: {...}             # ajustes de red propios (opcional)
```

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `nombre` | texto | — (obligatorio) | identificador: minúsculas, números, `-` y `_`, de 2 a 100 caracteres |
| `descripcion` | texto | `""` | se muestra en la interfaz |

## `descubrimiento`

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `dominios.permitir` | lista | `[]` | dominios permitidos; vacío = cualquiera |
| `dominios.bloquear` | lista | `[]` | dominios excluidos (ganan sobre `permitir`) |
| `fuentes` | lista | — (al menos una) | de dónde salen los sitios y documentos (ver abajo) |
| `exploracion` | mapa | ver abajo | cómo recorrer cada sitio encontrado |

**Patrones de dominio:** `sitio.org` y `*.sitio.org` incluyen el dominio y
todos sus subdominios (`www.sitio.org`, `datos.sitio.org`). Se aceptan con o
sin `http://`.

### Fuentes

Cada fuente lleva `tipo`. Al correr un perfil se pueden elegir cuáles usar,
por su índice (desde 0).

#### `semillas`

Páginas de inicio que se exploran. Si una URL ya es un documento (por su
extensión), se guarda directamente.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `urls` | lista de URL | — (al menos una) | páginas de inicio |

#### `lista_dominios`

Un CSV con un sitio por fila; se explora cada uno.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `archivo` | ruta | — | el CSV |
| `columna_dominio` | texto | `dominio` | columna con el dominio (o una URL; si trae ruta, se usa como semilla) |
| `columna_lugar` | texto | — | columna con la clave del lugar en el catálogo; cada documento del sitio hereda ese lugar. Exige `geografia` |

#### `buscador`

Consultas a un buscador web.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `motor` | `searxng` \| `brave` \| `serper` \| `serpapi` | — | SearXNG no necesita llave; los otros sí (ver [configuración](configuracion.md)) |
| `consultas` | lista | — (al menos una) | plantillas de consulta; `{variable}` se reemplaza |
| `variables` | mapa de listas \| ruta a CSV | — | mapa: una consulta por cada combinación. CSV: una consulta por fila (las columnas son las variables) |
| `usar` | `dominios` \| `documentos` | `dominios` | `dominios`: explora el sitio de cada resultado (el resultado va como semilla). `documentos`: guarda solo los resultados que ya son documentos |
| `max_resultados` | entero 1–100 | `20` | resultados por consulta |
| `columna_lugar` | texto | — | con `variables` en CSV: columna con la clave del lugar; lo encontrado hereda ese lugar. Exige `geografia` |

La validación revisa que cada `{variable}` usada exista en el mapa o en las
columnas del CSV. Las consultas repetidas se hacen una sola vez, y cada
consulta es una tarea aparte (se reparten entre trabajadores).

```yaml
- tipo: buscador
  motor: searxng
  consultas: ['"plan municipal de desarrollo" {municipio} {estado} filetype:pdf']
  variables: municipios.csv     # columnas municipio, estado, clave...
  columna_lugar: clave
  usar: documentos
```

#### `commoncrawl`

Documentos del índice público de Common Crawl, sin rastrear nada.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `patron` | texto | — | dominios a consultar, p. ej. `*.gob.mx` |
| `mime` | texto | `application/pdf` | tipo de archivo |
| `indices` | entero 1–12 | `1` | cuántos rastreos recientes consultar |
| `limite` | entero ≥ 1 | `10000` | máximo de documentos |

#### `wayback`

Documentos del índice del Internet Archive.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `patron` | texto | — | `*.sitio.org` (dominio y subdominios), `sitio.org/ruta/*` (prefijo) o un dominio |
| `mime` | texto | `application/pdf` | tipo de archivo |
| `limite` | entero ≥ 1 | `10000` | máximo de documentos |

### `exploracion`

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `sitemap` | sí/no | `true` | leer los sitemaps (los de robots.txt y `/sitemap.xml`) |
| `profundidad` | entero 0–10 | `2` | clics desde la portada o la semilla |
| `max_paginas` | entero 1–10000 | `40` | páginas por sitio |
| `tiempo_max_s` | entero ≥ 10 | `300` | segundos por sitio |
| `secciones_prioritarias` | lista | `[]` | palabras en la URL o el enlace que se visitan primero; si está vacía: documentos, descargas, publicaciones, biblioteca, transparencia, normatividad |
| `javascript` | sí/no | `false` | reservado para sitios hechos en JavaScript; todavía no tiene efecto (se avisa en la bitácora) |

También se visitan primero las páginas cuyo enlace menciona un tipo de
documento. Se descartan las redes sociales y los dominios estacionados.

## `documentos`

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `extensiones` | lista | `[pdf]` | qué cuenta como documento |
| `modo` | `palabras` \| `todos` | `palabras` | `palabras`: solo los que coinciden con un tipo. `todos`: cualquier documento |
| `tipos` | mapa | `{}` | tipos de documento (obligatorio al menos uno con `modo: palabras`) |
| `excluir` | lista | `[]` | palabras o frases que descartan un enlace (trámites, formatos...) |
| `puntaje_minimo` | entero 0–100 | `60` | puntaje para quedar aceptado (y descargarse) |
| `tamano_max_mb` | entero > 0 | — | tope por documento; si no, el global `almacen.tamano_max_mb` |

### Tipos

La clave del tipo (letras, números y `_`) es la que se guarda. Cada tipo
necesita al menos un patrón o una palabra.

| campo | tipo | qué hace |
|---|---|---|
| `nombre` | texto | nombre legible (también se le da a la IA para clasificar) |
| `patrones` | lista de expresiones regulares | se buscan sin distinguir mayúsculas |
| `palabras` | lista | palabras o frases literales (como palabra completa) |

Gana el primer tipo que coincide, en el orden en que están escritos.

**Cómo se compara el texto.** La URL y el texto del enlace se normalizan antes
de comparar:

- se decodifica `%20` y similares;
- se quitan los acentos y se pasa a minúsculas;
- los separadores (`_ - + . / \ = & ? :`) se vuelven espacios.

Así `PLAN_Municipal-de%20Desarrollo.pdf` queda como `plan municipal de
desarrollo pdf`. Escribe los patrones en minúsculas, sin acentos, y usa `\s*`
entre palabras para aceptar también nombres pegados
(`PlanMunicipalDeDesarrollo` → `planmunicipaldedesarrollo`):

```yaml
PMD:
  nombre: Plan municipal de desarrollo
  patrones: ['plan\s*municipal\s*de\s*desarrollo', '\b(pmd|pdm)\b']
```

### Puntaje

Cada candidato recibe un puntaje de 0 a 100 al encontrarse:

| condición | puntaje |
|---|---|
| el tipo aparece en el nombre del archivo | 85 |
| … en el texto del enlace | 80 |
| … solo en la ruta o la consulta de la URL | 50 |
| no coincide con ningún tipo | 0 |
| `modo: todos` (cualquier documento) | 70 |
| trae un año entre 1980 y 2035 | +10 |
| el nombre del archivo no dice nada (menos de 4 letras) y no hay texto de enlace | −15 |
| contiene una palabra de `excluir` | 0 (gana sobre todo lo demás) |

Queda **aceptado** si llega a `puntaje_minimo`. Tras cambiar los tipos,
`docubot candidatos recalificar <perfil>` recalcula los puntajes.

## `fichas`

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `ia` | sí/no | `true` | hacer fichas con IA (si hay proveedor configurado) |
| `campos` | mapa | `{}` | campos de la ficha (nombres en minúsculas, números y `_`) |
| `instrucciones` | texto | `""` | contexto extra para la IA |

Si el perfil tiene `tipos`, la IA también responde qué tipo de documento es,
sin saber cuál se esperaba; DocuBot lo compara y, si no coincide, la ficha
queda en revisión.

### Campos

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `tipo` | `texto` \| `fecha` \| `numero` \| `opcion` \| `lista` \| `lugar` | `texto` | cómo se valida |
| `requerido` | sí/no | `false` | si falta, la ficha queda en revisión |
| `opciones` | lista | `[]` | obligatorio con `opcion`; opcional con `lista` (solo valores de la lista) |
| `descripcion` | texto | `""` | guía para la IA y ayuda en el formulario |

| tipo | cómo se guarda |
|---|---|
| `texto` | texto; si es corto, las erratas se corrigen contra el texto del documento |
| `fecha` | `AAAA-MM-DD`, `AAAA-MM` o `AAAA` (acepta «5 de marzo de 2024», «05/03/2024»...) |
| `numero` | número |
| `opcion` | una de `opciones` (sin importar acentos ni mayúsculas) |
| `lista` | lista de textos |
| `lugar` | texto; se usa para ubicar el documento en el catálogo. Exige `geografia` |

## `geografia`

Catálogo de lugares para ubicar cada documento y verlo en el mapa.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `catalogo` | ruta | — | CSV de lugares |
| `poligonos` | ruta | — | GeoJSON con la forma de cada lugar |
| `campo_clave` | texto | `clave` | propiedad del GeoJSON con la clave del lugar |
| `nombre` | texto | nombre del archivo | con qué nombre se guarda el catálogo; varios perfiles pueden compartirlo |
| `niveles` | lista | `[]` | reservado; hoy no se usa (los niveles salen del CSV) |

**Formato del catálogo** (CSV con coma, punto y coma o tabulador):

| columna | obligatoria | qué es |
|---|---|---|
| `clave` | sí | identificador único del lugar |
| `nombre` | sí | nombre |
| `nivel` | sí | estado, municipio, provincia... |
| `padre` | no | clave del lugar que lo contiene |
| `alias` | no | otros nombres, separados por `\|` |
| `lat`, `lon` | no | punto en el mapa; si faltan, uno dentro de su polígono |

Un lugar se identifica siempre por su clave, nunca solo por su nombre. El
catálogo se importa al arrancar la API y al correr el perfil, y no se
reimporta si no cambió. Hay un catálogo de México en
[`config/catalogos/mexico`](../config/catalogos/mexico).

## `referencia`

Lo que ya se tiene, para marcar cada candidato como nuevo o ya conocido.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `archivo` | ruta | — | CSV con lo que ya se tiene |
| `llave` | lista | — (al menos una) | columnas que identifican un documento: `url` (se compara normalizada), `tipo`, `lugar`, `sha256` |

Cada columna de `llave` debe existir en el CSV. Con `sha256`, la marca se pone
al descargar; con las demás, al encontrar el candidato.

## `red`

Ajustes de red solo para este perfil; si no se ponen, se usan los globales.

| campo | tipo | omisión | qué hace |
|---|---|---|---|
| `peticiones_por_segundo_por_dominio` | número > 0 | global | ritmo por dominio |
| `respetar_robots` | sí/no | global | `false` ignora robots.txt (el ritmo se respeta igual) |

Al lanzar una corrida desde la interfaz también se pueden cambiar, solo para
esa vez: robots.txt, ritmo, profundidad, páginas por sitio y puntaje mínimo.

## Ejemplo completo

```yaml
nombre: reglamentos-municipales
descripcion: Reglamentos municipales publicados en sitios de gobierno

descubrimiento:
  dominios:
    permitir: ["*.gob.mx"]              # el dominio y sus subdominios
    bloquear: ["facebook.com"]
  fuentes:
    - tipo: semillas                    # fuente 0
      urls: [https://www.gob.mx/]
    - tipo: buscador                    # fuente 1
      motor: searxng
      consultas: ['reglamento municipal {tema} filetype:pdf']
      variables:
        tema: [tránsito, construcción, protección civil]   # 3 consultas
      usar: dominios                    # explora los sitios de los resultados
  exploracion:
    profundidad: 2
    max_paginas: 40
    secciones_prioritarias: [normatividad, reglamentos, transparencia]

documentos:
  extensiones: [pdf]
  modo: palabras
  tipos:
    REGLAMENTO:
      nombre: Reglamento municipal
      patrones: ['reglamento']          # texto ya normalizado: sin acentos, minúsculas
  excluir: [licencia, formato, solicitud]
  puntaje_minimo: 60

fichas:
  campos:
    titulo: { tipo: texto, requerido: true }
    fecha_publicacion: { tipo: fecha }
    materia: { tipo: opcion, opciones: [Tránsito, Construcción, Protección civil, Otra] }
    lugar: { tipo: lugar, descripcion: "municipio y estado al que aplica" }
  instrucciones: Son reglamentos de gobiernos municipales de México.

geografia:                              # obligatorio por el campo de tipo lugar
  catalogo: ../catalogos/mexico/lugares.csv
  poligonos: ../catalogos/mexico/lugares.geojson
  nombre: mexico

red:
  peticiones_por_segundo_por_dominio: 0.5
```
