FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias primero: si solo cambia el código, esta capa se reutiliza.
COPY pyproject.toml ./
RUN mkdir -p src/docubot && touch src/docubot/__init__.py \
    && pip install . && pip uninstall -y docubot && rm -rf src

COPY src ./src
COPY alembic.ini ./
RUN pip install --no-deps .

RUN useradd --create-home --uid 1000 docubot \
    && mkdir -p /datos/almacen /datos/modelos && chown -R docubot /datos
USER docubot

EXPOSE 8000
CMD ["docubot", "api", "--host", "0.0.0.0"]

# Imagen para correr las pruebas: docker compose --profile pruebas run --rm pruebas
FROM base AS pruebas
USER root
RUN pip install "pytest>=8.3" "pytest-asyncio>=0.24"
COPY tests ./tests
COPY pyproject.toml ./
USER docubot
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

# La imagen por omisión es la de la aplicación.
FROM base AS app
