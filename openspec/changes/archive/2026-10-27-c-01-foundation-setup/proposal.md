# Proposal: C-01 Foundation Setup

## Why

Para implementar el backend del Taller Mecánico según los requisitos obligatorios de la cátedra (UTN Programación III, Ejercicio 1), se necesita establecer los cimientos del proyecto: la estructura modular por capas, la configuración fuertemente tipada leída desde el entorno sin secretos en el código, el ciclo de vida asincrónico ASGI (`lifespan`) que gestione el motor y las sesiones en `app.state`, y los endpoints de verificación de salud (`/health/live` y `/health/ready`).

Sin esta base estructurada, cualquier desarrollo posterior correría el riesgo de incurrir en antipatrones como inicializar el motor de base de datos al importar módulos (antipatrón EA-08 que rompe el bucle de eventos en tests) o filtrar secretos en el repositorio.

## What Changes

- Creación del archivo `requirements.txt` con las versiones mínimas exactas exigidas por la consigna (`fastapi>=0.111`, `sqlmodel>=0.0.24`, `sqlalchemy>=2.0`, `asyncpg>=0.30`, `alembic>=1.13`, `pydantic-settings>=2.0`, `bcrypt>=4.0`, `pyjwt>=2.8`, `uvicorn[standard]`).
- Creación de `app/core/config.py` con la clase `Settings(BaseSettings)` de `pydantic-settings`, sin valores por defecto para secretos críticos (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`), y con la propiedad `@computed_field` para `DATABASE_URL` (`postgresql+asyncpg://...`).
- Creación de `env.example` documentando todas las variables requeridas sin exponer secretos.
- Creación de `app/core/database.py` que provee funciones para crear el motor asincrónico, la fábrica de sesiones con `expire_on_commit=False`, y la dependencia `get_session()` que obtiene la sesión desde `app.state`.
- Creación de `main.py` con el contexto asincrónico `lifespan` que inicializa el motor en `app.state.engine`, precalcula el hash ficticio de bcrypt para mitigación de timing attacks, y asegura el cierre ordenado con `engine.dispose()`.
- Montaje de los dos grupos de rutas en `main.py`: grupo abierto (rutas públicas y auth) y grupo protegido.
- Implementación de `app/modules/health/router.py` con:
  - `GET /health/live`: Responde HTTP 200 `{"status": "live"}` inmediatamente sin tocar la base de datos.
  - `GET /health/ready`: Ejecuta `SELECT 1` sobre PostgreSQL; responde HTTP 200 `{"status": "ready"}` o HTTP 503 `{"status": "database unavailable"}` ante fallos de conectividad.
- Creación de `app/core/paginacion.py` con el DTO genérico `PaginacionWrapper[T]` y el envoltorio estándar `{items, total, page, size, pages}`, validando límites de paginación (size 1..100, página válida o 422).
- Suite de tests unitarios y de integración para validar la configuración, el ciclo de vida ASGI y los endpoints `/health/*`.

## Capabilities

### New Capabilities

- `health`: Endpoints de monitoreo operativo y sondas de salud (`/health/live` para comprobar que el proceso web está vivo y `/health/ready` para verificar conectividad con la base de datos PostgreSQL mediante `SELECT 1`).
- `app-lifecycle`: Ciclo de vida ASGI (`lifespan`), configuración centralizada tipada mediante `Settings(BaseSettings)` con `pydantic-settings`, gestión del motor asincrónico y pool en `app.state`, precalculo de hash ficticio para mitigación de timing attacks, y estructura base de paginación.

### Modified Capabilities

*(Ninguna, este es el change inicial del proyecto).*

## Impact

- **Código base y arquitectura**: Establece el esqueleto del proyecto (`app/core/`, `app/modules/health/`) y define el estándar de inicialización asincrónica para todos los módulos subsiguientes.
- **APIs**: Expone `/health/live` y `/health/ready`.
- **Dependencias**: Introduce las dependencias base de Python especificadas en la consigna en `requirements.txt`.
- **Variables de Entorno**: Establece el contrato de configuración en `env.example`.
