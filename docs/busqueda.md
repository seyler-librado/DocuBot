# Búsqueda

La pantalla **Buscar** (atajo: `/` desde cualquier pantalla) busca dentro de
todos los documentos.

| modo | cómo busca |
|---|---|
| **Palabras** | texto completo en español, sin acentos y por raíz: «planeacion» encuentra «Planeación» y «reglamentos» encuentra «reglamento» |
| **Por tema** | documentos que hablan de lo mismo aunque usen otras palabras: «cuidado del medio ambiente» encuentra el reglamento ambiental aunque no diga «cuidado» |
| **Mixta** | las dos combinadas. Es la que se usa por omisión |

Cada resultado trae los pasajes que coinciden, con su página; al abrirlo, el
visor va directo a esa página. Se puede filtrar por perfil, tipo de documento
y estado de la ficha.

## Por palabras

- Postgres con una configuración propia (`docubot_es`): español, sin acentos
  y por raíz.
- La ficha pesa más que el cuerpo, y su título más que el resto de la ficha.
- **Consultas normales:** basta con algunas palabras, y los documentos que
  tienen todas quedan arriba. Pedirlas todas dejaba fuera documentos buenos
  que no usan una de ellas.
- **Sintaxis de buscador**, que se respeta tal cual:

  | escribes | encuentra |
  |---|---|
  | `"agua potable"` | la frase exacta |
  | `reglamento -tránsito` | sin la palabra excluida |
  | `atlas OR riesgos` | una u otra |

- Se indexan hasta 400 mil caracteres por documento (unas 150 páginas).

## Por tema

El texto de cada documento se parte en fragmentos (`busqueda.tamano_fragmento`,
900 caracteres por omisión, con solape y sin cruzar páginas), y cada fragmento
se convierte en un vector. Una consulta encuentra los fragmentos más
parecidos.

| `busqueda.embeddings` | qué usa |
|---|---|
| `local` (omisión) | un modelo chico multilingüe en CPU, dentro del contenedor: `paraphrase-multilingual-MiniLM-L12-v2`, unos 220 MB, unos 100 fragmentos por segundo. Sin GPU ni llaves; se descarga una vez y se guarda en el volumen `modelos` |
| `ollama`, `openai`, `openai_compat` | el endpoint `/v1/embeddings` de ese servidor (`busqueda.modelo`, `busqueda.url`, `busqueda.llave`) |
| `ninguno` | solo búsqueda por palabras |

- **Umbral:** todo texto se parece un poco a otro, así que solo entran los
  documentos con similitud ≥ `busqueda.similitud_minima` (0.45) y cerca del
  mejor resultado (`busqueda.ventana_similitud`).
- **Acervos muy parejos:** si todo son documentos del mismo tipo, una consulta
  genérica («reglas para…») se parece a casi todos. El orden sigue siendo
  útil, y la búsqueda mixta lo compensa.
- **Cambiar de modelo** obliga a volver a indexar: los vectores de modelos
  distintos no se comparan.

Cada documento con texto se indexa solo, después de extraerlo (etapa
**indexar**). Para lo que falte, o tras cambiar de modelo:

```bash
docubot busqueda indexar              # lo que falte
docubot busqueda indexar --rehacer    # todo
docubot busqueda buscar "multas de tránsito" --modo mixta
```

## Mixta

Las dos listas se combinan por posición (*Reciprocal Rank Fusion*): un
documento que aparece arriba en ambas gana a uno que solo aparece en una.
