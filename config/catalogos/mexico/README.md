# Catálogo de lugares: México

Estados y municipios de México para ubicar documentos en el mapa.

| archivo | contenido |
|---|---|
| `lugares.csv` | 32 estados y 2,475 municipios: `clave`, `nombre`, `nivel`, `padre`, `alias` (separados por `\|`), `lat`, `lon` |
| `lugares.geojson` | polígono simplificado de cada lugar, con su clave en `properties.clave` |

- **Claves:** las del Marco Geoestadístico de INEGI (estado `13`, municipio
  `13077`). Un documento se ubica por clave, nunca solo por nombre: 88 nombres
  de municipio se repiten en más de un estado.
- **Coordenadas:** las de la cabecera municipal.
- **Alias:** la cabecera cuando se llama distinto al municipio (Benito Juárez →
  Cancún), la forma corta (Tulancingo de Bravo → Tulancingo) y algunos nombres
  comunes de estados (CDMX, Edomex, Q. Roo).
- **Estado de México:** se llama así completo, para que la palabra «México»,
  que aparece en casi todo documento, no lo active.

**Fuente:** INEGI, Marco Geoestadístico (catálogo único de claves y límites
municipales), datos abiertos de libre uso. Los polígonos están simplificados
para el mapa; no sirven para análisis espacial fino.

## Usarlo en un perfil

```yaml
geografia:
  catalogo: ../catalogos/mexico/lugares.csv
  poligonos: ../catalogos/mexico/lugares.geojson
  nombre: mexico
```

Con un CSV de municipios que traiga su clave (columna `columna_lugar`), cada
documento hereda su lugar de la fila que lo encontró. Si no, DocuBot lo
deduce del texto y de la ficha.

Para otro país o región, arma los mismos dos archivos con tus propias claves.
