# Cómo contribuir

¡Gracias por querer mejorar DocuBot! Todo cambio es bienvenido: código,
perfiles de ejemplo, catálogos de lugares de otros países, documentación o
reportes de errores.

## Antes de empezar

- **Errores e ideas:** abre un *issue* con la plantilla que corresponda.
  Para errores, incluye el perfil (sin datos privados), qué esperabas, qué
  pasó y la bitácora (`docker compose logs worker`).
- **Cambios grandes:** coméntalos primero en un *issue* para acordar el
  enfoque.

## Preparar el entorno

```bash
cp .env.example .env
docker compose up -d --build
```

- **Backend** (`backend/`): Python 3.12, FastAPI, SQLAlchemy async, Alembic.
- **Interfaz** (`frontend/`): React, Vite, TypeScript y Tailwind.
  `npm run dev` sirve la interfaz con recarga en vivo contra la API de Docker.

## Antes de mandar un *pull request*

```bash
# pruebas (usan su propia base de datos, docubot_pruebas)
docker compose --profile pruebas run --rm --build pruebas

# estilo del backend
cd backend && ruff check src tests && ruff format --check src tests

# la interfaz compila
cd frontend && npm run build
```

El CI corre lo mismo en cada *pull request*.

## Convenciones

- **Idioma:** el código, los mensajes y la documentación están en español.
  Nombres claros sobre nombres cortos.
- **Pruebas:** todo cambio de comportamiento lleva su prueba. Las de red usan
  servidores simulados (`tests/simulado.py`); nunca la red real.
- **Base de datos:** si cambias `db/modelos.py`, genera la migración:

  ```bash
  docker compose run --rm -v ./backend/src:/app/src -e PYTHONPATH=/app/src \
    migrar alembic revision --autogenerate -m "lo que cambió"
  ```

  Revísala a mano y comprueba con `docker compose exec api alembic check`.
- **Nada privado en el repositorio:** llaves y direcciones van en `.env`;
  los proveedores propios, en `config/extensiones/`; y los perfiles propios,
  en `config/perfiles/`. Ninguna de esas carpetas se versiona.
- **Perfiles de ejemplo:** van en `ejemplos/<nombre>/perfil.yaml`, con sus
  archivos al lado. La prueba `tests/test_ejemplos.py` los valida.

## Licencia

Al contribuir aceptas que tu aporte se publique bajo la [licencia MIT](LICENSE).
