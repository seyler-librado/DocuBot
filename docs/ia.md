# Texto, fichas e IA

## Extraer el texto

Cada documento descargado pasa por la etapa **extraer**:

- **Con texto:** el de todas sus páginas (pypdf, con pypdfium2 de respaldo
  para PDFs dañados), con un tope de 3 millones de caracteres.
- **Escaneado:** casi no tiene capa de texto; la IA lo leerá por imagen.
- **Ilegible:** no abre (dañado, protegido), y se dice por qué.

## La ficha

La etapa **fichar** le da a la IA las primeras páginas (`ia.paginas`, 12 por
omisión) o, si el documento está escaneado, las primeras como imagen
(`ia.paginas_imagen`). Le pide los campos de `fichas.campos` del perfil.

- **El prompt se arma solo** con los campos del perfil: su tipo, sus opciones
  y su descripción. `fichas.instrucciones` agrega contexto.
- **Clasificación a ciegas:** a la IA no se le dice qué tipo de documento se
  espera; elige entre los tipos del perfil u «Otro», y DocuBot compara. Si se
  le da la pista, casi siempre le da la razón.
- **Si no cabe**, se recorta el texto y se reintenta.

La respuesta se valida campo por campo:

| tipo de campo | qué se hace |
|---|---|
| `texto` | espacios normalizados; si es corto (título, nombres), cada palabra que no aparece tal cual en el documento se cambia por la más parecida que sí («MUCIPAL» → «MUNICIPAL», acentos incluidos) |
| `fecha` | `05/03/2024`, `5 de marzo de 2024` o `2024-3-5` → `2024-03-05` (o `AAAA-MM`, `AAAA`) |
| `numero` | el número, sin separadores de miles |
| `opcion` | una de las opciones, sin importar acentos ni mayúsculas (tolera erratas) |
| `lista` | elementos sin repetir; si el campo tiene opciones, solo las válidas |
| `lugar` | texto; se usa para [ubicar el documento](geografia.md) |

Cada ficha queda:

| estado | cuándo |
|---|---|
| `ok` | sin problemas graves |
| `revision` | falta un campo obligatorio, la IA dice que es otro tipo de documento o el título no aparece en el texto |
| `ilegible` | no se pudo leer el documento |
| `error` | la IA no devolvió una ficha legible |

Además lleva confianza (alta, media, baja; las leídas por imagen llegan a
media como máximo) y los motivos. Las dudosas aparecen en **Revisión**, y
cualquier ficha se puede corregir, aprobar o rehacer desde la pantalla del
documento.

```bash
docubot fichas 3              # texto y fichas de lo ya descargado en la corrida 3
docubot fichas 3 --rehacer    # rehacerlas (p. ej. tras cambiar los campos del perfil)
```

## Proveedores

Se eligen en `config/docubot.yaml` (`ia.proveedor`) o en `.env`
(`DOCUBOT_IA__PROVEEDOR`). La llave va siempre en `.env`.

| proveedor | qué es | qué configurar |
|---|---|---|
| `ninguno` | sin fichas: se descarga y se extrae el texto | — |
| `ollama` | IA local | `docker compose --profile ollama up -d`, luego `docker compose exec ollama ollama pull <modelo>` y `DOCUBOT_IA__MODELO=<modelo>` |
| `openai` | OpenAI | `DOCUBOT_IA__MODELO`, `DOCUBOT_IA__LLAVE` |
| `openai_compat` | cualquier servidor con la API de OpenAI: Groq, OpenRouter, LM Studio, vLLM, Gemini... | además `DOCUBOT_IA__URL` (la raíz `/v1`) |
| `anthropic` | Claude | `DOCUBOT_IA__MODELO`, `DOCUBOT_IA__LLAVE` |
| `archivo.py:Clase` | un proveedor propio | ver abajo |

- **Para Ollama** conviene un modelo con visión, que también lea los
  escaneados. Con tarjeta NVIDIA, quita los comentarios de `deploy:` del
  servicio `ollama` en `docker-compose.yml`.
- **Cuántas fichas a la vez:** `trabajadores.ia`. Una por omisión, porque un
  modelo local o un servidor compartido no agradece más.
- **¿Responde?** `docubot ia probar`, o el botón Probar en Ajustes.

### Proveedores propios

Si tu IA tiene su propia API, escribe una clase en `config/extensiones/` y
apúntale con `DOCUBOT_IA__PROVEEDOR=archivo.py:Clase`. Esa carpeta no se
versiona (salvo el ejemplo), así que tus direcciones no llegan al repositorio.
Instrucciones y ejemplo: [config/extensiones/README.md](../config/extensiones/README.md).

## ¿Qué tan bien lo hace? El conjunto dorado

Para comparar modelos o ajustar un perfil, arma una carpeta con algunos PDFs y
un `dorado.csv` con la ficha correcta de cada uno:

```csv
archivo,titulo,fecha_publicacion,instancias,tipo_documento
plan-tula.pdf,Plan Municipal de Desarrollo 2024-2027,2024-03-05,H. Ayuntamiento|IMPLAN,PMD
atlas-pachuca.pdf,Atlas de Riesgos de Pachuca de Soto,2019,,ATLAS
```

- `archivo` es el PDF, relativo a la carpeta.
- Va una columna por campo a medir; las listas se separan con `|`.
- `tipo_documento` (opcional) es la clave del tipo según el perfil.

```bash
docker compose exec api docubot ia evaluar /app/config/evaluacion/mi-conjunto \
  --perfil mi-perfil --salida /datos/almacen/evaluacion.json
```

```
12 documento(s) · aciertos: 84.4 %

  titulo                  91.7 %  ██████████████████  (11/12)
  fecha_publicacion       83.3 %  █████████████████   (10/12)
  instancias              75.0 %  ███████████████     (9/12)
  tipo_documento          91.7 %  ██████████████████  (11/12)
```

Cómo se compara cada campo:
- **Textos:** por parecido (≥ 85 %, sin acentos ni mayúsculas).
- **Fechas, números y opciones:** exactos.
- **Listas:** deben compartir al menos la mitad de los elementos.
- **Campo vacío en el CSV:** es acierto si la IA también lo dejó vacío.

Pon tus conjuntos en `config/evaluacion/`: el contenedor ve esa carpeta como
`/app/config/evaluacion`.
