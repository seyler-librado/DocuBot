# Postgres 16 con pgvector (búsqueda semántica) y PostGIS (lugares y polígonos).
# Las extensiones se activan en la primera migración (CREATE EXTENSION).
FROM pgvector/pgvector:0.8.0-pg16

# Algunas redes bloquean las descargas que se identifican como apt de Debian.
# Si te pasa, define APT_USER_AGENT en .env (p. ej. "Mozilla/5.0").
ARG APT_USER_AGENT=""

RUN if [ -n "$APT_USER_AGENT" ]; then \
        echo "Acquire::http::User-Agent \"$APT_USER_AGENT\";" > /etc/apt/apt.conf.d/99user-agent; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99user-agent
