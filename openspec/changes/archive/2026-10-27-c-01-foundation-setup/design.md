# Design: C-01 Foundation Setup

## Context

El proyecto inicia desde un repositorio vacío con las especificaciones y reglas canónicas definidas en `knowledge-base/` y `AGENTS.md`. Este primer change establece la arquitectura base del servidor asincrónico, las convenciones de configuración y las sondas de monitoreo requeridas por el Ejercicio 1 de la cátedra. Ver `proposal.md` para la motivación general y `specs/` para los requerimientos normativos.

## Goals / Non-Goals

**Goals:**
- Establecer el scaffolding de directorios canónicos (`app/core/`, `app/modules/health/`, `tests/`).
- Implementar la gestión de configuración tipada mediante `Settings(BaseSettings)` con `pydantic-settings` y `@computed_field` para `DATABASE_URL` (`postgresql+asyncpg://`).
- Implementar el gestor de ciclo de vida ASGI `lifespan` que inicialice el motor en `app.state.engine`, precalcule el hash ficticio de bcrypt y cierre conexiones con `engine.dispose()`.
- Proveer la fábrica de sesiones asincrónicas con `expire_on_commit=False` y la dependencia `get_session()`.
- Montar en `main.py` los dos grupos de rutas canónicos: abierto y protegido.
- Implementar los endpoints `/health/live` y `/health/ready` con intercepción de errores de base de datos (HTTP 503).
- Implementar `PaginacionWrapper[T]` con validaciones de límites de paginación (1..100).
- Diseñar la suite de tests unitarios y de integración con `pytest-asyncio` y `httpx.AsyncClient`.

**Non-Goals:**
- No se modelan tablas de dominio ni migraciones de Alembic (se abordarán en C-02).
- No se implementa la lógica de autenticación ni tokens JWT (se abordará en C-04).
- No se construyen los repositorios ni el Unit of Work de dominio (se abordarán en C-03).

## Decisions

### Decision 1: Gestión de Ciclo de Vida ASGI en `lifespan` vs Engine Global
- **Elección**: Usar un gestor de contexto asincrónico `@asynccontextmanager def lifespan(app: FastAPI)` en `main.py`, almacenando el motor en `app.state.engine` y la fábrica de sesiones en `app.state.session_factory`.
- **Racionalidad**: Evita el antipatrón EA-08 (creación de recursos asincrónicos al importar módulos antes de que exista el event loop), asegurando que los tests y el servidor compartan el mismo bucle de eventos. Al apagar el servidor, se ejecuta `await engine.dispose()`.
- **Alternativas consideradas**:
  - Motor global instanciado en `app/core/database.py`: Provoca errores de `RuntimeError: Task attached to a different loop` al alternar entre tests y runner.
  - Eventos `@app.on_event("startup")`: Obsoletos y desaconsejados en versiones modernas de FastAPI.

### Decision 2: Configuración con `pydantic-settings` y Sin Valores por Defecto para Secretos
- **Elección**: Definir `Settings(BaseSettings)` leyendo variables desde `.env` o el entorno del sistema. Las variables `POSTGRES_PASSWORD` y `JWT_SECRET_KEY` no tienen valor por defecto.
- **Racionalidad**: Si falta una credencial crítica, la aplicación no debe iniciar bajo ninguna circunstancia. La URL se genera dinámicamente mediante `@computed_field` con el formato `postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}`.
- **Alternativas consideradas**:
  - Variable monolítica `DATABASE_URL`: Difícil de componer en entornos donde el usuario y password se inyectan por separado; la cátedra exige las variables sueltas.

### Decision 3: Precalculo del Hash Ficticio en el Lifespan
- **Elección**: Calcular una única vez durante el startup un hash válido de bcrypt y almacenarlo en `app.state.dummy_hash`.
- **Racionalidad**: Requisito explícito de la consigna para mitigar timing attacks en el endpoint de login (RN-09). Precalcularlo al inicio evita gastar ciclos de CPU generando hashes ficticios en cada solicitud fallida.

### Decision 4: Fábrica de Sesiones con `expire_on_commit=False`
- **Elección**: Configurar `async_sessionmaker(..., expire_on_commit=False)`.
- **Racionalidad**: En SQLAlchemy asincrónico, el comportamiento por defecto de expirar instancias tras el commit provoca errores al intentar acceder a atributos de modelos fuera de la transacción activa (intento de lazy load implícito).

### Decision 5: Estructura de Paginación Estándar (`PaginacionWrapper[T]`)
- **Elección**: Modelo Pydantic genérico `PaginacionWrapper[T]` con atributos `{items: list[T], total: int, page: int, size: int, pages: int}` y método utilitario para calcular `pages`.
- **Racionalidad**: Establece el contrato único de respuesta para todos los listados de la API (consigna Sección 2.9).

## Risks / Trade-offs

- **[Riesgo: Demora excesiva en `/health/ready` si PostgreSQL está saturado o inaccesible]** → *Mitigación*: Ejecutar `SELECT 1` envuelto con `asyncio.wait_for` con un timeout acotado (ej. 2 segundos), respondiendo inmediatamente HTTP 503 ante timeout.
- **[Riesgo: Incompatibilidad de tests unitarios que no dispongan de PostgreSQL activo]** → *Mitigación*: Implementar fixtures en `pytest` que permitan sobrescribir `app.state` o mockear la sesión para verificar el comportamiento de `/health/ready` tanto en éxito (200) como en fallo (503).
