# Cambios

## 0.1.0 — primera versión pública

- **Perfiles YAML** con validación y mensajes en español: dominios, fuentes,
  exploración, tipos de documento, campos de ficha, geografía, referencia y
  red.
- **Descubrimiento:**
  - fuentes: semillas, listas de dominios, buscadores (SearXNG, Brave, Serper,
    SerpAPI), Common Crawl y Wayback;
  - explorador de sitios con sitemaps, prioridades, límites y detección de
    documentos sin extensión y en visores externos;
  - robots.txt, ritmo por dominio, reintentos y respaldo para certificados
    vencidos.
- **Calificación** por puntaje y **descarga** con varios hilos:
  - almacén por sha256;
  - validación de PDFs;
  - respaldo en el Internet Archive.
- **Texto y fichas con IA:**
  - proveedores Ollama, OpenAI, compatibles con OpenAI, Anthropic y propios;
  - validación por tipo de campo y corrección de erratas;
  - estado, confianza y revisión;
  - evaluación contra un conjunto dorado.
- **Geografía:**
  - catálogos de lugares en PostGIS, con el de México (INEGI);
  - ubicación por clave cruzando fuente y contenido, con desambiguación de
    nombres repetidos;
  - mapa.
- **Búsqueda:** por palabras (texto completo en español), por tema (vectores,
  con un modelo local en CPU) y mixta.
- **Interfaz web en vivo:**
  - pantallas: panel, búsqueda, perfiles, corridas, biblioteca, documento con
    visor PDF y ficha editable, mapa, revisión, candidatos y ajustes;
  - tema claro y oscuro, también en el celular.
- **Pipeline** sobre una cola en Postgres que se reanuda sola.
- **Ejemplos:** planeación municipal en México, normas oficiales mexicanas y
  ordenanzas municipales de España.
