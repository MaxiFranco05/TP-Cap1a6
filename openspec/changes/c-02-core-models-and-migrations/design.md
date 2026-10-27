# Design: C-02 Core Models and Migrations

## Context

El proyecto ya cuenta con `app/core/config.py`, `app/core/database.py` y el ciclo de vida ASGI en `main.py` (`C-01`). Ahora debemos definir los 13 modelos relacionales distribuidos en 4 módulos (`usuarios`, `clientes`, `repuestos`, `ordenes`) y configurar Alembic con plantilla asincrónica para producir las dos migraciones exigidas por la consigna (`001_initial_schema.py` y `002_append_only_triggers.py`). Ver `proposal.md` para la motivación y `specs/database-schema/spec.md` para los requisitos normativos.

## Goals / Non-Goals

**Goals:**
- Modelar las 13 tablas con `SQLModel(..., table=True)` respetando los nombres exactos de tablas y columnas de la consigna oficial.
- Garantizar que todas las columnas `datetime` se mapeen a `DateTime(timezone=True)` (`TIMESTAMPTZ`) y todos los montos monetarios a `Numeric(10, 2)` / `Numeric(12, 2)` con `Decimal`.
- Declarar índices explícitos en todas las claves foráneas (`index=True`), restricciones `CheckConstraint`, `UniqueConstraint` e índices únicos parciales con `Index(..., unique=True, postgresql_where=text(...))`.
- Evitar ciclos de importación entre los 4 módulos de modelos registrándolos limpiamente para el `SQLModel.metadata` que consume `migrations/env.py`.
- Proveer un `docker-compose.yml` con PostgreSQL 16 para desarrollo y pruebas de migración locales.

**Non-Goals:**
- No se implementan en este change los esquemas DTO de entrada/salida (`schemas.py`), repositorios (`repository.py`), Unit of Work (`unit_of_work.py`), servicios ni routers de negocio (corresponden a `C-03`..`C-08`).
- No se pueblan las filas del catálogo `estado_orden` dentro de las migraciones; la consigna establece explícitamente que las migraciones crean la tabla vacía y `seed.py` (`C-09`) carga los datos.

## Decisions

### 1. Mapeo explícito de `TIMESTAMPTZ` y `NUMERIC` en SQLModel
- **Decisión**: Usar `sa_column=Column(DateTime(timezone=True), nullable=...)` (o `sa_type=DateTime(timezone=True)`) para todos los campos `datetime` y `sa_column=Column(Numeric(10, 2), nullable=False)` / `Numeric(12, 2)` para importes en `Decimal`.
- **Alternativas consideradas**: Dejar el mapeo por defecto de `datetime` en SQLModel (que genera `TIMESTAMP WITHOUT TIME ZONE` en PostgreSQL) o usar `max_digits`/`decimal_places` sin verificar el DDL generado.
- **Justificación**: PostgreSQL diferencia estrictamente `timestamp` de `timestamptz`. La regla dura #9 y la página 6 de la consigna exigen que todas las fechas sean `timestamptz` y el dinero `NUMERIC`.

### 2. Índices únicos parciales con `sqlalchemy.Index` y `postgresql_where`
- **Decisión**: Definir en `__table_args__` de `AsignacionRol`, `Vehiculo` y `Repuesto` objetos `Index` con `unique=True` y `postgresql_where=text("revocada_en IS NULL")` / `text("borrado_en IS NULL")`:
  - `ix_asignacion_rol_usuario_rol_vigente` en `asignacion_rol (usuario_id, rol) WHERE revocada_en IS NULL`
  - `ix_vehiculo_patente_vigente` en `vehiculo (patente) WHERE borrado_en IS NULL`
  - `ix_repuesto_codigo_vigente` en `repuesto (codigo) WHERE borrado_en IS NULL`
- **Alternativas consideradas**: `UniqueConstraint` estándar.
- **Justificación**: Un `UNIQUE` común impide reasignar un rol revocado o volver a registrar la patente de un vehículo dado de baja (`RN-01`, `RN-03`, pág. 6).

### 3. Navegación bidireccional y resolución de referencias cruzadas entre módulos
- **Decisión**:
  - Usar `TYPE_CHECKING` e importaciones diferidas por nombre de clase en `Relationship(...)` para evitar importaciones circulares entre `usuarios`, `clientes`, `repuestos` y `ordenes`.
  - En `Usuario.cliente`, configurar `Relationship(back_populates="usuario", sa_relationship_kwargs={"uselist": False})` para que `usuario.cliente` devuelva un objeto `Cliente | None` y no una lista (exigencia explícita del Ejercicio 2, pág. 11).
  - En tablas con múltiples FKs hacia la misma tabla (`AsignacionRol` tiene `usuario_id` y `otorgada_por` hacia `usuario.id`; `HistorialEstadoOrden` tiene `desde_estado` y `hasta_estado` hacia `estado_orden.codigo`), especificar `sa_relationship_kwargs={"foreign_keys": "[...]"}` para que SQLAlchemy resuelva sin ambigüedad las relaciones.

### 4. Configuración de Alembic asincrónico sin secretos en `alembic.ini`
- **Decisión**: En `alembic.ini`, dejar `sqlalchemy.url =` vacío (sin credenciales ni valores por defecto, cumpliendo los requisitos no funcionales de pág. 19). En `migrations/env.py`, importar `get_settings()` desde `app.core.config`, importar los 4 módulos de modelos (`app.modules.usuarios.models`, `app.modules.clientes.models`, `app.modules.repuestos.models`, `app.modules.ordenes.models`) y usar `async_engine_from_config` / `create_async_engine(settings.DATABASE_URL)` con `connection.run_sync(do_run_migrations)`.
- **Justificación**: Permite que `alembic revision --autogenerate`, `alembic upgrade head` y `alembic downgrade base` funcionen directamente con las variables de entorno / `.env` usando el driver `asyncpg`.

### 5. Separación en 2 migraciones (`001` autogenerada y `002` manual con triggers PL/pgSQL)
- **Decisión**:
  - `001_initial_schema.py`: Generada con `alembic revision --autogenerate`, revisada e identificada con un comentario inicial indicando que fue leída antes de aplicarse.
  - `002_append_only_triggers.py`: Escrita a mano con una función PL/pgSQL `rechazar_mutacion_solo_agregado()` que lanza `RAISE EXCEPTION` ante `UPDATE` o `DELETE`, y 3 triggers (`trg_historial_estado_orden_solo_agregado`, `trg_movimiento_stock_solo_agregado`, `trg_historial_precio_repuesto_solo_agregado`). Su `downgrade()` elimina los 3 triggers y la función PL/pgSQL.
- **Justificación**: Cumple exactamente con el Ejercicio 2 y el Ejercicio 7 (`RN-15`), garantizando reversibilidad completa (`upgrade head` -> `downgrade base` -> `upgrade head`).

## Risks / Trade-offs

- **[Risk] Ambigüedad de `MultipleForeignKeys` en SQLAlchemy** (`asignacion_rol` hacia `usuario` y `historial_estado_orden` hacia `estado_orden`) → **Mitigation**: Declarar explícitamente `foreign_keys` en `sa_relationship_kwargs` de cada `Relationship` afectado y cubrir la inicialización del mapeador (`configure_mappers()`) en tests unitarios.
- **[Risk] `autogenerate` de Alembic requiere conexión activa a PostgreSQL 16** → **Mitigation**: Incluir `docker-compose.yml` con `postgres:16-alpine` alineado con `env.example` para levantar el contenedor y ejecutar tanto la generación como las pruebas de integración de migraciones y triggers.

## Migration Plan

1. Levantar contenedor PostgreSQL 16 con `docker compose up -d`.
2. Ejecutar `alembic upgrade head` sobre base vacía (aplica `001` y `002`).
3. Verificar reversibilidad con `alembic downgrade base` y re-aplicar `alembic upgrade head`.
