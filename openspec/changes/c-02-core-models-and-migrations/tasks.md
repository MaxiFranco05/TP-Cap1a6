# Tasks: C-02 Core Models and Migrations

## 1. Modelos SQLModel de Usuarios y Clientes

- [x] 1.1 Escribir tests unitarios en `tests/test_models.py` verificando la estructura de `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente` y `vehiculo` (nombres de columnas, tipos `TIMESTAMPTZ`, índices en FKs, `CHECK` de rol y año `1950..2100`, índices únicos parciales `postgresql_where`, y relación `Usuario.cliente` con `uselist=False`).
- [x] 1.2 Implementar `app/modules/usuarios/models.py` (`Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad`) y `app/modules/clientes/models.py` (`Cliente`, `Vehiculo`), ejecutando `pytest tests/test_models.py` hasta pasar en verde.

## 2. Modelos SQLModel de Repuestos y Órdenes de Trabajo

- [x] 2.1 Ampliar `tests/test_models.py` para verificar `repuesto`, `movimiento_stock`, `historial_precio_repuesto`, `estado_orden`, `orden_trabajo`, `item_orden` e `historial_estado_orden` (tipos `NUMERIC(10,2)` y `NUMERIC(12,2)`, `TIMESTAMPTZ`, índice único parcial en `repuesto.codigo`, `UNIQUE(orden_id, repuesto_id)`, `CHECK` constraints, FKs a `estado_orden.codigo` con índices y configuración completa de mappers de SQLAlchemy).
- [x] 2.2 Implementar `app/modules/repuestos/models.py` (`Repuesto`, `MovimientoStock`, `HistorialPrecioRepuesto`) y `app/modules/ordenes/models.py` (`EstadoOrden`, `OrdenTrabajo`, `ItemOrden`, `HistorialEstadoOrden`), verificando que todos los tests de `tests/test_models.py` pasen en verde.

## 3. Infraestructura PostgreSQL 16 y Configuración de Alembic Asincrónico

- [x] 3.1 Crear `docker-compose.yml` con PostgreSQL 16 y archivo `.env` local de desarrollo (no versionado), levantar el contenedor y verificar conectividad con `GET /health/ready` / `asyncpg`.
- [x] 3.2 Configurar `alembic.ini` (sin credenciales hardcodeadas) y `migrations/env.py` con soporte asincrónico (`run_migrations_online` usando `get_settings().DATABASE_URL` y `SQLModel.metadata` con los 13 modelos importados), verificando que `alembic current` ejecute sin errores.

## 4. Migraciones 001 (Esquema Inicial) y 002 (Triggers de Sólo Agregado)

- [x] 4.1 Escribir tests de integración en `tests/test_migrations.py` que validen el ciclo `alembic upgrade head` -> `alembic downgrade base` -> `alembic upgrade head`, la presencia de los 3 índices únicos parciales en PostgreSQL y el rechazo de `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (`RN-15`).
- [x] 4.2 Generar la migración `migrations/versions/001_initial_schema.py` con `alembic revision --autogenerate`, revisarla asegurando las 13 tablas, tipos `TIMESTAMPTZ`/`NUMERIC`, FKs con índices, `CHECK` constraints e índices únicos parciales (`postgresql_where`), y agregar el comentario de revisión manual al inicio.
- [x] 4.3 Escribir a mano la migración `migrations/versions/002_append_only_triggers.py` con su comentario de revisión, la función PL/pgSQL `rechazar_mutacion_solo_agregado()` y los 3 disparadores `BEFORE UPDATE OR DELETE` en `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (incluyendo su `downgrade`), y verificar que `pytest tests/test_migrations.py` y toda la suite pasen en verde.
