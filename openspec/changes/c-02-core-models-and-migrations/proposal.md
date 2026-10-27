# Proposal: C-02 Core Models and Migrations

## Why

La API necesita materializar el modelo de dominio relacional completo en PostgreSQL 16 (las 13 tablas obligatorias de usuarios, clientes, repuestos y órdenes) delegando en el motor de base de datos las garantías estructurales de integridad: unicidad, claves foráneas indexadas, restricciones `CHECK`, índices únicos parciales para borrado lógico y vigencia de roles (`RN-01`, `RN-03`), catálogo textual para estados de órdenes (`RN-19`) y disparadores de sólo agregado (`RN-15`). Sin este esquema versionado exclusivamente mediante Alembic (sin usar `create_all`), no es posible construir los repositorios, el Unit of Work ni los módulos funcionales posteriores.

## What Changes

- **Modelos SQLModel del dominio de Usuarios (`app/modules/usuarios/models.py`)**:
  - Tabla `usuario`: `id`, `email` (`UNIQUE`), `nombre`, `password_hash`, `activo`, `debe_cambiar_password`, `password_cambiada_en` (`timestamptz`, nulo permitido) y relación `1 a 0..1` hacia `Cliente` (`Usuario.cliente` devuelve un objeto único `Cliente | None`, nunca una lista).
  - Tabla `asignacion_rol`: `id`, `usuario_id` (FK a `usuario.id` con índice), `rol` (`CHECK rol IN ('ADMIN', 'RECEPCION', 'MECANICO', 'CLIENTE')`), `desde` (`timestamptz`), `vence_en` (`timestamptz`, nulo), `revocada_en` (`timestamptz`, nulo), `otorgada_por` (FK a `usuario.id` con índice, nulo) e índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL` (`RN-03`).
  - Tabla `intento_acceso`: `id`, `cuando` (`timestamptz`), `email`, `ip`, `exito` e índice compuesto `(email, ip, cuando)`.
  - Tabla `evento_seguridad`: `id`, `cuando` (`timestamptz`), `actor` (`str`), `accion` (`str`).
- **Modelos SQLModel del dominio de Clientes y Vehículos (`app/modules/clientes/models.py`)**:
  - Tabla `cliente`: `id`, `usuario_id` (FK a `usuario.id`, `UNIQUE`, índice, nulo permitido), `nombre`, `documento` (`UNIQUE`), `telefono` y navegación bidireccional con `Usuario` y `Vehiculo`.
  - Tabla `vehiculo`: `id`, `cliente_id` (FK a `cliente.id` con índice), `patente`, `marca`, `modelo`, `anio` (`CHECK anio BETWEEN 1950 AND 2100`), `borrado_en` (`timestamptz`, nulo) e índice único parcial `(patente) WHERE borrado_en IS NULL` (`RN-01`).
- **Modelos SQLModel del dominio de Repuestos (`app/modules/repuestos/models.py`)**:
  - Tabla `repuesto`: `id`, `codigo`, `descripcion`, `precio` (`NUMERIC(10,2)`, `CHECK precio > 0`), `stock` (`CHECK stock >= 0`), `borrado_en` (`timestamptz`, nulo) e índice único parcial `(codigo) WHERE borrado_en IS NULL` (`RN-01`).
  - Tabla `movimiento_stock`: `id`, `repuesto_id` (FK a `repuesto.id` con índice), `orden_id` (FK a `orden_trabajo.id` con índice, nulo permitido), `usuario_id` (FK a `usuario.id` con índice), `cantidad` (`CHECK cantidad <> 0`), `motivo`, `cuando` (`timestamptz`).
  - Tabla `historial_precio_repuesto`: `id`, `repuesto_id` (FK a `repuesto.id` con índice), `usuario_id` (FK a `usuario.id` con índice), `precio_anterior` (`NUMERIC(10,2)`), `precio_nuevo` (`NUMERIC(10,2)`, `CHECK precio_nuevo > 0`, `CHECK precio_nuevo <> precio_anterior`), `cuando` (`timestamptz`).
- **Modelos SQLModel del dominio de Órdenes (`app/modules/ordenes/models.py`)**:
  - Tabla `estado_orden` (catálogo): `codigo` (PK textual), `descripcion`, `posicion` (`UNIQUE`), `es_final` (`bool`).
  - Tabla `orden_trabajo`: `id`, `vehiculo_id` (FK a `vehiculo.id` con índice), `mecanico_id` (FK a `usuario.id` con índice, nulo permitido), `estado` (FK a `estado_orden.codigo` con índice), `falla`, `creada_en` (`timestamptz`), `total` (`NUMERIC(12,2)`, `CHECK total >= 0`).
  - Tabla `item_orden`: `id`, `orden_id` (FK a `orden_trabajo.id` con índice), `repuesto_id` (FK a `repuesto.id` con índice), `cantidad` (`CHECK cantidad > 0`), `precio_unitario` (`NUMERIC(10,2)`, `CHECK precio_unitario > 0`), `UNIQUE (orden_id, repuesto_id)`.
  - Tabla `historial_estado_orden`: `id`, `orden_id` (FK a `orden_trabajo.id` con índice), `desde_estado` (FK a `estado_orden.codigo` con índice, nulo permitido), `hasta_estado` (FK a `estado_orden.codigo` con índice), `usuario_id` (FK a `usuario.id` con índice), `cuando` (`timestamptz`).
- **Configuración de Alembic asincrónico y 2 migraciones (`alembic.ini`, `migrations/`)**:
  - `migrations/env.py` configurado con plantilla asincrónica leyendo `get_settings().DATABASE_URL` (sin credenciales en `alembic.ini`) y registrando todos los metadatos de SQLModel.
  - Migración `001_initial_schema.py`: generada con `--autogenerate`, creando las 13 tablas, FKs indexadas, restricciones `CHECK`, tipos `NUMERIC` y `TIMESTAMPTZ`, e índices únicos parciales (`postgresql_where`).
  - Migración `002_append_only_triggers.py`: escrita a mano, instalando la función PL/pgSQL y los 3 disparadores (`BEFORE UPDATE OR DELETE`) sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (`RN-15`).
  - Ambas migraciones incluyen el comentario explícito de revisión previa exigido por la cátedra y soportan ciclo completo `upgrade head` -> `downgrade base` -> `upgrade head`.

## Capabilities

### New Capabilities
- `database-schema`: Esquema relacional de las 13 tablas obligatorias en SQLModel/PostgreSQL, tipos de datos estrictos (`NUMERIC`, `TIMESTAMPTZ`), claves foráneas indexadas, navegación bidireccional (`1:1`, `1:N`), restricciones `CHECK`, índices únicos parciales (`postgresql_where`) y versionado de migraciones con Alembic asincrónico (`001` autogenerada y `002` manual con triggers de sólo agregado).

### Modified Capabilities
<!-- Ninguna capacidad existente modifica sus requisitos -->

## Impact

- **Nuevos archivos de modelos**:
  - `app/modules/usuarios/__init__.py`, `app/modules/usuarios/models.py`
  - `app/modules/clientes/__init__.py`, `app/modules/clientes/models.py`
  - `app/modules/repuestos/__init__.py`, `app/modules/repuestos/models.py`
  - `app/modules/ordenes/__init__.py`, `app/modules/ordenes/models.py`
- **Infraestructura de migraciones**:
  - `alembic.ini`
  - `migrations/env.py`, `migrations/script.py.mako`, `migrations/README`
  - `migrations/versions/001_initial_schema.py`
  - `migrations/versions/002_append_only_triggers.py`
  - `docker-compose.yml` (servicio PostgreSQL 16 local para desarrollo y verificación de migraciones)
- **Pruebas automatizadas**:
  - `tests/test_models.py` y `tests/test_migrations.py`
