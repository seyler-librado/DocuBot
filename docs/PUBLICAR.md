# Lista para publicar en GitHub

El repositorio está listo; solo falta subirlo. Esta guía se puede borrar
después de publicar.

## 1. Decidido

- **Repositorio:** `seyler-librado/DocuBot`.
- **Licencia:** MIT (`LICENSE`).
- **Autor de los *commits*:** `seyler-librado
  <353518062+seyler-librado@users.noreply.github.com>` (el correo privado de
  GitHub, configurado solo en este repositorio).
- **Historial:** se publica un solo *commit* limpio; el historial de desarrollo
  queda en la rama local `historial`, que no se sube.
- Las direcciones provisionales ya apuntan a
  `https://github.com/seyler-librado/DocuBot`.

## 2. Subirlo

1. En GitHub, con la cuenta seyler-librado, crea el repositorio `DocuBot`
   **vacío** (sin README, licencia ni `.gitignore`).
2. En esta carpeta:

   ```bash
   git remote add origin git@github-seyler:seyler-librado/DocuBot.git
   git push -u origin main
   ```

3. En el repositorio, en GitHub:
   - [ ] **Actions:** el CI corre en el primer *push*; espera a que salga en verde.
   - [ ] **Settings → Code security:** activa *Private vulnerability
     reporting* (lo pide `SECURITY.md`) y Dependabot.
   - [ ] **About:** descripción («Descubre, descarga y cataloga documentos
     públicos según perfiles configurables») y temas (`web-scraping`,
     `document-management`, `llm`, `postgis`, `pgvector`, `fastapi`,
     `react`, `spanish`).
4. [ ] **Primera versión:** crea la etiqueta `v0.1.0` con las notas de
   `CHANGELOG.md` (*Releases → Draft a new release*).

## Lo que ya se revisó

- **Nada privado en lo versionado.** Se buscó en todos los *commits*: no hay
  llaves, direcciones de servidores, rutas de la máquina ni referencias
  institucionales. El historial de desarrollo mencionaba por nombre el
  servidor de IA de pruebas; por eso no se publica.
- **Lo local queda fuera de git:** `.env`, `config/perfiles/` (salvo el
  ejemplo), `config/extensiones/` (salvo el ejemplo), `config/evaluacion/` y
  `almacen/`.
- **Datos de terceros:** el catálogo de México viene de INEGI (datos
  abiertos), los dominios municipales de Wikidata y patrones públicos, y el
  mapa base de OpenStreetMap, con su atribución.
