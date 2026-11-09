# Geografía y mapa

Si el perfil tiene `geografia`, cada documento se ubica en un lugar de un
catálogo (país, estado, municipio, provincia...) y aparece en el **Mapa**.

## El catálogo

Dos archivos, junto al perfil o en `config/catalogos/`:

| archivo | contenido |
|---|---|
| CSV | `clave`, `nombre`, `nivel` y, opcionales, `padre` (clave del lugar que lo contiene), `alias` (separados por `\|`), `lat`, `lon` |
| GeoJSON (opcional) | el polígono de cada lugar, con su clave en `properties.<campo_clave>` |

```yaml
geografia:
  catalogo: ../catalogos/mexico/lugares.csv
  poligonos: ../catalogos/mexico/lugares.geojson
  campo_clave: clave        # propiedad del GeoJSON con la clave
  nombre: mexico            # cómo se guarda en la base (varios perfiles pueden compartirlo)
```

Se importa solo (al arrancar la API y al crear una corrida) y no se reimporta
si no cambió. Si un lugar no trae coordenadas pero sí polígono, su punto es
uno dentro del polígono.

**Viene un catálogo de México** en `config/catalogos/mexico`: 32 estados y
2,475 municipios, con claves y polígonos de INEGI y alias útiles (Benito
Juárez → Cancún, Tulancingo de Bravo → Tulancingo, CDMX, Edomex). Ver su
[README](../config/catalogos/mexico/README.md). Para otro país, arma los mismos
dos archivos con tus claves.

## Cómo se ubica un documento

**Un lugar se identifica por su clave, nunca solo por su nombre.** En México,
88 nombres de municipio se repiten en más de un estado (Benito Juárez existe
en 7).

La etapa **ubicar** cruza dos capas:

1. **La fuente.** Si el documento salió de una fila con clave de lugar (un
   CSV de municipios con `columna_lugar`), hereda ese lugar.
2. **El contenido.** Busca los nombres y alias del catálogo en el título, en el
   campo de tipo `lugar` de la ficha y en el texto, y los pesa:
   - **El contexto:** «municipio de…», «ayuntamiento de…» favorecen al
     municipio; «estado de…», «gobierno del estado» favorecen al estado. Así
     «Estado de Hidalgo» no se confunde con el municipio de Hidalgo.
   - **El lugar que lo contiene:** si el estado aparece en otra parte del
     texto, el municipio con ese nombre sube. Así se separan los homónimos.
   - **Las palabras comunes:** «Reforma» es un municipio, pero también una
     palabra de cualquier reglamento. Una sola palabra cuenta la mitad en el
     cuerpo del texto, y cada nombre cuenta a lo sumo 3 veces.
   - **El protagonista:** un municipio nombrado de pasada no le gana a un
     estado protagonista («Reglamento del Congreso del Estado de Durango»).

| fuente | contenido | resultado |
|---|---|---|
| L | coincide o menciona L | L, por la fuente y el texto |
| L | no dice nada | L, por la fuente |
| L | apunta con fuerza a otro lugar y L ni se menciona | L, **en revisión**, con ambos candidatos |
| — | un lugar claro | ese lugar, por el texto |
| — | un nombre que comparten varios lugares | **ambiguo**, con los candidatos |
| — | nada | sin lugar |

Lo dudoso aparece en **Revisión → Lugares por decidir**, donde se elige con
un clic. En cada documento, «Dónde aplica» muestra el lugar y deja cambiarlo.
Lo elegido a mano no se vuelve a pisar.

```bash
docubot lugares importar mi-perfil    # reimportar el catálogo
docubot lugares ubicar 3              # volver a ubicar lo de la corrida 3
```

## El mapa

- Los lugares del nivel más detallado se sombrean según cuántos documentos
  tienen; los del nivel general (estados) también, más tenue, si tienen
  documentos propios.
- Cada lugar con documentos tiene un punto: ámbar si alguno está en revisión.
- Al hacer clic en un lugar se abre la lista de sus documentos.

El mapa base es OpenStreetMap (`mapa.teselas` y `mapa.atribucion` en
`config/docubot.yaml`; respeta su política de uso). Los polígonos del catálogo
se dibujan encima, así que aun sin internet se ve el contorno.
