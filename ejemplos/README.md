# Perfiles de ejemplo

Perfiles listos para copiar y adaptar. Cada uno es una carpeta con su
`perfil.yaml` y los archivos que usa.

```bash
cp -r ejemplos/planeacion-municipal-mx config/perfiles/
docker compose exec api docubot perfiles validar
```

Después aparece en la pantalla **Perfiles**, listo para correr.

| ejemplo | qué busca | lo interesante |
|---|---|---|
| [`planeacion-municipal-mx`](planeacion-municipal-mx) | planes municipales de desarrollo, desarrollo urbano, atlas de riesgos, ordenamiento, movilidad y reglamentos urbanos de México | lista de los 2,475 municipios con su clave INEGI y los 1,642 dominios conocidos; 8 tipos de documento; catálogo de lugares y mapa |
| [`normas-oficiales-mx`](normas-oficiales-mx) | Normas Oficiales Mexicanas (NOM) y normas mexicanas (NMX) | buscador por materia y Common Crawl; ficha con clave, dependencia y materia |
| [`ordenanzas-municipales-es`](ordenanzas-municipales-es) | ordenanzas municipales de España | otro país y otro dominio (`*.es`), sin catálogo de lugares |

Las fuentes de tipo `buscador` necesitan SearXNG (gratis:
`docker compose --profile searxng up -d`) o la llave de un buscador. Al correr
un perfil, la pantalla deja elegir qué fuentes usar.

## `planeacion-municipal-mx/municipios.csv`

Una fila por municipio: `clave` (INEGI, 5 dígitos), `municipio`, `estado` y
`dominio` (vacío si no se conoce). Los dominios se reunieron de Wikidata y de la
forma habitual `municipio.gob.mx`; no todos están verificados y algunos cambian
con cada administración. Los que ya no responden quedan como «sin respuesta» en
la corrida. Si encuentras uno mejor, corrígelo y comparte el cambio.
