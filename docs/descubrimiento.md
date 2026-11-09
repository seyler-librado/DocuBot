# Descubrimiento y descarga

Cómo DocuBot pasa de un perfil a documentos descargados. La referencia de
cada campo del YAML está en [perfiles.md](perfiles.md).

```
fuentes ─► sitios ─► explorar ─► candidatos (con puntaje) ─► descargar ─► documentos
```

## Corridas

Una **corrida** toma un perfil y lo ejecuta. Guarda una copia del perfil, así
que cambiar el YAML a media corrida no la altera (las fichas, los lugares y la
búsqueda sí siguen el perfil actual).

- Se lanza con el botón **Correr** de la pantalla Perfiles. Ahí también se
  eligen las fuentes y se ajustan, solo para esa corrida, robots.txt, el
  ritmo, la profundidad, las páginas por sitio y el puntaje mínimo.
- Desde la terminal: `docubot correr <perfil>`.
- Se puede **detener** y **reanudar**: cada tarea vive en una cola en Postgres,
  así que un worker reiniciado sigue donde quedó.
- Termina sola cuando ya no le quedan tareas.

## Fuentes

| tipo | qué hace | cuándo usarla |
|---|---|---|
| `semillas` | explora las URLs que le das (si una es un documento, la guarda directo) | pocos sitios conocidos |
| `lista_dominios` | explora cada dominio de un CSV; la fila puede traer la clave de su lugar | un universo conocido: todos los municipios, todas las universidades... |
| `buscador` | una consulta por combinación de variables o por fila de CSV. Con `usar: dominios` explora los sitios que aparecen; con `usar: documentos` guarda solo los documentos directos | descubrir sitios que no conoces, o documentos sueltos |
| `commoncrawl` | documentos del índice público de Common Crawl (miles de millones de páginas ya rastreadas) | barrer un dominio completo sin rastrearlo tú |
| `wayback` | documentos del índice del Internet Archive | documentos que ya no están en línea |

El buscador se reparte en una tarea por consulta, así que varias corren a la
vez y una corrida interrumpida no repite las ya hechas.

### Buscadores

| motor | costo | configuración |
|---|---|---|
| SearXNG | gratis | `docker compose --profile searxng up -d` (busca en varios motores a la vez) |
| Brave Search API | con llave | `DOCUBOT_BUSCADORES__BRAVE_LLAVE` |
| Serper (Google) | con llave | `DOCUBOT_BUSCADORES__SERPER_LLAVE` |
| SerpAPI (Google) | con llave | `DOCUBOT_BUSCADORES__SERPAPI_LLAVE` |

Si falta una llave, la tarea falla de inmediato y dice qué variable definir.

## Exploración de un sitio

1. **Portada:** prueba `https://`, `http://`, con y sin `www`. Si redirige a
   una red social o a un dominio estacionado («este dominio está en venta»),
   el sitio se marca y no se sigue. Un dominio que no resuelve DNS falla al
   instante.
2. **Sitemaps:** los que declara robots.txt y `/sitemap.xml`.
3. **Recorrido por prioridad:** primero las semillas, luego las páginas cuyo
   enlace o URL menciona una sección prioritaria o un tipo de documento.
   Respeta la profundidad, el máximo de páginas y el tiempo máximo por sitio.
4. **Qué cuenta como documento:**
   - la extensión del enlace;
   - un enlace sin extensión que parece descarga (`descargar.php?id=7`): se
     confirma con HEAD;
   - una página que al pedirla responde con un PDF;
   - un visor de Google Drive, Docs, Dropbox u OneDrive, que se convierte en
     enlace de descarga directa.

### Buenos modales

- Se identifica con su propio user agent (`red.user_agent`).
- Respeta robots.txt, también en cada salto de una redirección. Se puede
  desactivar en `config/docubot.yaml`, por perfil o por corrida, pero el ritmo
  por dominio se respeta siempre.
- Ritmo por dominio: 1 petición por segundo por omisión, o el `Crawl-delay`
  del sitio si es mayor.
- Reintentos con espera creciente ante errores pasajeros (5xx, 429, sin
  conexión), respetando `Retry-After`.
- Muchos sitios públicos tienen certificados vencidos: si la verificación TLS
  falla, reintenta sin verificar y lo anota.

Para ver cómo pide DocuBot una URL: `docubot red probar https://sitio/`.

## Calificación

Cada candidato recibe un puntaje de 0 a 100 en cuanto aparece:

| dónde aparece el tipo de documento | puntaje |
|---|---|
| en el nombre del archivo | 85 |
| en el texto del enlace | 80 |
| solo en la ruta o la consulta | 50 |
| en ninguna parte | 0 |

- **+10** si trae un año (1980–2035).
- **−15** si el nombre del archivo no dice nada y no hay texto de enlace.
- **0** si tiene una palabra de `documentos.excluir`.
- En `modo: todos`, cualquier documento parte de 70.

Los que llegan a `documentos.puntaje_minimo` quedan **aceptados**; los demás,
**rechazados**, siempre con el motivo. Si un candidato reaparece con mejor
puntaje (por ejemplo, ahora con texto de enlace), se acepta. En la pantalla
Candidatos se puede aceptar o rechazar a mano.

Si cambias los tipos de un perfil: `docubot candidatos recalificar <perfil>`.

## Descarga

- Los aceptados se descargan conforme aparecen, primero los de mayor puntaje,
  con `trabajadores.descarga` hilos y el ritmo por dominio.
- **Almacén por huella:** cada archivo vive en `almacen/ab/cd/<sha256>.<ext>`.
  El mismo documento en dos URLs se guarda una vez.
- **Validación:** detecta páginas HTML disfrazadas de PDF, PDFs incompletos
  (sin `%%EOF`) y archivos vacíos.
- **Respaldo:** si el documento ya no está (404, dominio inexistente,
  incompleto, HTML), intenta la copia del Internet Archive. Si tampoco sirve,
  el candidato queda «fallido» con su motivo.
- **Lo nuevo:** con `referencia` en el perfil (un CSV con lo que ya tienes),
  cada candidato queda marcado como nuevo o ya conocido.

```bash
docubot correr mi-perfil --sin-descargar      # solo descubrir y calificar
docubot descargar 3 --limite 50               # bajar los 50 mejores de la corrida 3
docubot descargar 3 --fallidos                # reintentar los que fallaron
```

Después de descargar, cada documento sigue su camino: [texto y ficha](ia.md),
[lugar](geografia.md) e [índice de búsqueda](busqueda.md).
