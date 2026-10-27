# Tasks: C-01 Foundation Setup

## 1. Configuración de Entorno y Dependencias

- [x] 1.1 Crear `requirements.txt` con las versiones mínimas exactas exigidas por la consigna (`fastapi>=0.111`, `sqlmodel>=0.0.24`, `sqlalchemy>=2.0`, `asyncpg>=0.30`, `alembic>=1.13`, `pydantic-settings>=2.0`, `bcrypt>=4.0`, `pyjwt>=2.8`, `uvicorn[standard]`, `pytest`, `pytest-asyncio`, `httpx`) y verificar su consistencia.
- [x] 1.2 Crear plantilla `env.example` documentando todas las variables requeridas sin secretos.
- [x] 1.3 Escribir tests unitarios en `tests/test_config.py` para validar la lectura de `Settings`, el cálculo dinámico de `DATABASE_URL` (`postgresql+asyncpg://`) y el rechazo en startup si faltan `POSTGRES_PASSWORD` o `JWT_SECRET_KEY`.
- [x] 1.4 Implementar `app/core/config.py` con `Settings(BaseSettings)` y `@computed_field` para `DATABASE_URL`, verificando que `test_config.py` pase en verde.

## 2. Motor de Base de Datos y Ciclo de Vida ASGI

- [x] 2.1 Escribir tests en `tests/test_database.py` y `tests/test_lifecycle.py` verificando la inicialización del motor en `app.state.engine`, la fábrica de sesiones con `expire_on_commit=False`, el precalculo de `app.state.dummy_hash` y el cierre ordenado con `dispose()`.
- [x] 2.2 Implementar `app/core/database.py` con las funciones de creación del motor asincrónico, la fábrica de sesiones y la dependencia `get_session()`.
- [x] 2.3 Implementar `main.py` con el manejador de ciclo de vida `@asynccontextmanager def lifespan(app: FastAPI)` y el montaje inicial de los dos grupos de rutas (`router_abierto` y `router_protegido`), verificando que los tests de ciclo de vida pasen en verde.

## 3. Endpoints de Salud (Health Checks)

- [x] 3.1 Escribir tests en `tests/test_health.py` para `GET /health/live` (código HTTP 200 sin tocar base de datos) y `GET /health/ready` (código HTTP 200 con `SELECT 1` o HTTP 503 ante falla/timeout de base de datos).
- [x] 3.2 Implementar `app/modules/health/router.py` con las rutas `/health/live` y `/health/ready` e incluir el router en el grupo abierto de `main.py`, verificando que `test_health.py` pase en verde.

## 4. Envoltorio Estándar de Paginación

- [x] 4.1 Escribir tests unitarios en `tests/test_paginacion.py` para el DTO genérico `PaginacionWrapper[T]`, validando formato `{items, total, page, size, pages}`, cálculo de `pages` y límites de `size` (1..100) y `page` (>= 1).
- [x] 4.2 Implementar `app/core/paginacion.py` y verificar que los tests de paginación pasen en verde.

## 5. Verificación de Integración y Entrega

- [x] 5.1 Ejecutar la suite completa de tests automatizados con `pytest` confirmando que todos los escenarios pasen.
- [x] 5.2 Crear el archivo `test/health.http` documentando las llamadas de prueba para `/health/live` y `/health/ready`.
