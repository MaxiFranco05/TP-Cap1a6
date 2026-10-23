# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **Taller Mecánico API (TP Cap 1 a 6)**.
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están en `openspec/changes/archive/`).
2. Leer los docs de la knowledge-base indicados en "Leer antes".
3. Ejecutar `/opsx:propose <nombre-del-change>`.
4. Al terminar el change, archivarlo con `/opsx:archive <nombre-del-change>`.
5. Marcar el checkbox `[x]` en este archivo.

---

## Árbol de dependencias

```
C-01 foundation-setup
  └── C-02 core-models-and-migrations
        └── C-03 base-repositories-and-uow
              └── C-04 auth-and-passwords
                    └── C-05 rbac-authorization-and-isolation    ← DESBLOQUEA DOMINIOS OPERATIVOS
                          │
                          ├── C-06 clientes-and-vehiculos        ← PARALELO con C-07
                          │     │
                          │     └── C-08 ordenes-and-background-tasks (requiere C-06 y C-07)
                          │           └── C-09 seed-and-test-suite
                          │
                          └── C-07 repuestos-and-inventario      ← PARALELO con C-06
                                └── (converge en C-08)
```

### Paralelismo por fase

> Cada "gate" es un punto de sincronización. Los changes dentro de un grupo pueden ejecutarse en paralelo.

```
GATE 0: ninguna
  → C-01 foundation-setup                    (solo)

GATE 1: C-01 ✓
  → C-02 core-models-and-migrations         (solo)

GATE 2: C-02 ✓
  → C-03 base-repositories-and-uow          (solo)

GATE 3: C-03 ✓
  → C-04 auth-and-passwords                 (solo)

GATE 4: C-04 ✓
  → C-05 rbac-authorization-and-isolation   (solo)

GATE 5: C-05 ✓                              ← PRIMER FORK (2 paralelos)
  → C-06 clientes-and-vehiculos             [Agente A]
  → C-07 repuestos-and-inventario           [Agente B]

GATE 6: C-06 + C-07 ✓
  → C-08 ordenes-and-background-tasks       [Agente A]

GATE 7: C-08 ✓
  → C-09 seed-and-test-suite                [Agente A]
```

### Camino crítico (8 changes — mínimo irreducible)

```
C-01 → C-02 → C-03 → C-04 → C-05 → C-07* → C-08 → C-09
```

> *Nota*: C-06 y C-07 tienen la misma longitud de rama (1 change); cualquiera de las dos ramas forma parte del camino crítico de 8 steps irreducible.

### Plan óptimo con 3 agentes

```
Paso │ Agente A (Core & Dominio)            │ Agente B (Inventario & Clientes)     │ Agente C (Testing & Auditoría)
─────┼──────────────────────────────────────┼──────────────────────────────────────┼───────────────────────────────
  1  │ C-01 foundation-setup                │                  —                   │               —
  2  │ C-02 core-models-and-migrations     │                  —                   │               —
  3  │ C-03 base-repositories-and-uow      │                  —                   │               —
  4  │ C-04 auth-and-passwords              │                  —                   │               —
  5  │ C-05 rbac-authorization-and-isolation│                  —                   │               —
  6  │ C-06 clientes-and-vehiculos          │ C-07 repuestos-and-inventario        │               —
  7  │ C-08 ordenes-and-background-tasks   │                  —                   │               —
  8  │                  —                   │                  —                   │ C-09 seed-and-test-suite
```

---

## FASE 0 — Cimientos y Configuración

### [C-01] `foundation-setup`
- **Estado**: `[ ]` pendiente
- **Scope**: Scaffolding del monorepo + configuración centralizada + lifespan ASGI + health checks
  - Scaffolding del proyecto y configuración de dependencias en `requirements.txt`: Python 3.12, FastAPI >=0.111, SQLModel >=0.0.24, SQLAlchemy 2.0 (asincrónico), asyncpg >=0.30, Alembic >=1.13, pydantic-settings >=2.0, bcrypt >=4.0, PyJWT >=2.8, uvicorn
  - Módulo `app/core/config.py`: Definición de clase `Settings(BaseSettings)` con tipado estricto para `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRATION_SECONDS`, `COOKIE_SECURE`, `BCRYPT_ROUNDS`, `BCRYPT_MAX_CONCURRENCY`, `DB_POOL_SIZE`, `SQL_ECHO` y `@computed_field` para `DATABASE_URL` asincrónica (`postgresql+asyncpg://`)
  - Archivo `env.example` con plantilla documentada y archivo `.env` local sin secretos versionados en git
  - Módulo `app/core/database.py`: Creación del motor asincrónico `create_async_engine`, generador de fábrica de sesiones `async_sessionmaker(expire_on_commit=False)` y dependencia FastAPI `get_session()`
  - Archivo `main.py`: Inicialización de la aplicación FastAPI, configuración del ciclo de vida ASGI `lifespan` que almacena motor en `app.state.engine`, precalcula hash ficticio de bcrypt al inicio y asegura el cierre ordenado con `await engine.dispose()`. Montaje inicial de los dos grupos de rutas: abierto y protegido
  - Módulo `app/modules/health/router.py`: Endpoints `GET /health/live` (responde HTTP 200 `{"status": "live"}` inmediatamente sin consultar la base de datos) y `GET /health/ready` (ejecuta `SELECT 1` sobre PostgreSQL; responde HTTP 200 `{"status": "ready"}` o HTTP 503 `{"status": "database unavailable"}`)
  - Módulo `app/core/paginacion.py`: DTO genérico `PaginacionWrapper[T]` con contrato estándar `{items: list[T], total: int, page: int, size: int, pages: int}`, validación de límites (size entre 1 y 100, page >= 1 o 422) y cálculo de páginas
  - Tests: Verificación de ciclo de vida ASGI, carga de variables de entorno y validación de respuestas HTTP de salud (Casos oficiales C-01 y C-02)
- **Dependencias**: ninguna
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/01_vision_y_objetivos.md` §Objetivos y Alcance
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico
  - `knowledge-base/06_funcionalidades.md` §US-001 (Monitoreo /health)
  - `knowledge-base/08_arquitectura_propuesta.md` §Configuración y Variables de Entorno
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-08 (Creación de motor en lifespan ASGI)

---

## FASE 1 — Persistencia, Modelos Relacionales y Triggers

### [C-02] `core-models-and-migrations`
- **Estado**: `[ ]` pendiente
- **Scope**: Definición de los 13 modelos relacionales SQLModel, restricciones CHECK, relaciones, índices parciales y dos migraciones Alembic
  - Modelos relacionales SQLModel con restricciones de integridad y tipos obligatorios:
    - `app/modules/usuarios/models.py`: Tablas `usuario` (`email` único, `password_hash`, `activo`, `debe_cambiar_password`, `password_cambiada_en`), `asignacion_rol` (`rol` CHECK con `ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`, `desde`, `vence_en`, `revocada_en`, índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL`), `intento_acceso` (índice en `email, ip, cuando`), `evento_seguridad`
    - `app/modules/clientes/models.py`: Tablas `cliente` (`documento` único, `usuario_id` FK único opcional), `vehiculo` (`cliente_id` FK, `patente`, `marca`, `modelo`, CHECK `anio BETWEEN 1950 AND 2100`, `borrado_en: timestamptz`, índice único parcial `(patente) WHERE borrado_en IS NULL`)
    - `app/modules/repuestos/models.py`: Tablas `repuesto` (`codigo`, CHECK `precio > 0` con `NUMERIC(10,2)`, CHECK `stock >= 0`, `borrado_en: timestamptz`, índice único parcial `(codigo) WHERE borrado_en IS NULL`), `movimiento_stock` (CHECK `cantidad <> 0`, `motivo`, `usuario_id`, `cuando`), `historial_precio_repuesto` (`precio_anterior`, CHECK `precio_nuevo > 0` y `precio_nuevo <> precio_anterior`)
    - `app/modules/ordenes/models.py`: Tablas `estado_orden` (catálogo con PK textual `codigo`, `descripcion`, `posicion` único, `es_final`), `orden_trabajo` (`vehiculo_id`, `mecanico_id` nulo inicial, `estado` FK a catálogo, `falla`, CHECK `total >= 0` con `NUMERIC(12,2)`), `item_orden` (`orden_id`, `repuesto_id`, CHECK `cantidad > 0`, CHECK `precio_unitario > 0`, restricción `UNIQUE (orden_id, repuesto_id)`), `historial_estado_orden` (`desde_estado`, `hasta_estado`, `usuario_id`, `cuando`)
  - Configuración de Alembic: `alembic.ini` y `migrations/env.py` con soporte para conexión asincrónica (`run_migrations_online` con `async_engine.connect()`)
  - Migración 001 (`migrations/versions/001_initial_schema.py`): Creación de las 13 tablas, claves foráneas, restricciones de chequeo (CHECK), tipos `timestamptz` y `NUMERIC`, e índices únicos parciales de borrado lógico
  - Migración 002 (`migrations/versions/002_append_only_triggers.py`): Creación de función PL/pgSQL `rechazar_mutacion_solo_agregado()` y 3 triggers PostgreSQL para rechazar cualquier `UPDATE` o `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (RN-15)
  - Tests: Validación de `alembic upgrade head`, verificación de esquema en PostgreSQL y test de reversibilidad (`alembic downgrade base` y re-upgrade)
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Diccionario de Entidades y Tablas Obligatorias
  - `knowledge-base/05_reglas_de_negocio.md` §RN-01 (Unicidad y Borrado Lógico), §RN-15 (Sólo Agregado)
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones (Append-Only) y Estructura de Directorios
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-04 (Alembic y Triggers), §DD-05 (Catálogo textual), §DD-06 (Índices parciales)

---

## FASE 2 — Abstracción Transaccional y Repositorios

### [C-03] `base-repositories-and-uow`
- **Estado**: `[ ]` pendiente
- **Scope**: Repositorios genéricos reutilizables y patrón Unit of Work asincrónico base
  - Módulo `app/core/repository.py`:
    - Clase genérica `BaseRepository[T]`: Métodos asincrónicos `get(id)`, `list(skip, limit)`, `add(instance)`, `update(instance)`, `delete(instance)`. Regla arquitectónica estricta: ejecuta exclusivamente `await session.flush()`, **nunca** `commit()`
    - Clase `SoftDeleteRepository[T]`: Especialización de `BaseRepository` que filtra automáticamente entidades con `borrado_en IS NULL`, expone `soft_delete(id)` para asentar la fecha de baja lógica y `list_active(skip, limit)`
    - Clase `ReadOnlyRepository[T]`: Repositorio inmutable que solo expone métodos de lectura (`get`, `list`), omitiendo cualquier operación de escritura (para catálogo `estado_orden`)
    - Soporte unificado de precarga (`eager loading`) mediante `selectinload` para relaciones jerárquicas y compuestas, previniendo antipatrón de consultas N+1
  - Módulo `app/core/unit_of_work.py`:
    - Clase base abstracta `AbstractUnitOfWork`: Gestor de contexto asincrónico (`async with uow:`) que controla la sesión SQLAlchemy
    - Manejo atómico del ciclo de transacción: `await session.commit()` al finalizar el contexto sin errores, y `await session.rollback()` automático ante excepciones
  - Manejo global de excepciones de persistencia en `main.py`:
    - Interceptor de `IntegrityError` de SQLAlchemy/asyncpg que traduce errores de clave única a HTTP 409 Conflict y errores de restricción a HTTP 422, sin exponer el texto interno de PostgreSQL ni la estructura de tablas (RN-18)
    - Manejador de `DataError` y errores de conversión evitando cualquier HTTP 500 no controlado
  - Tests: Pruebas unitarias de aislamiento transaccional del UoW, verificación de rollback en excepciones, pruebas de `SoftDeleteRepository` y verificación de intercepción de errores de base de datos
- **Dependencias**: C-02
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/02_descripcion_general.md` §Arquitectura general (Capas estrictas)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-18 (Intercepción de errores de base de datos)
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones (Unit of Work, Repository, Read-Only, Eager Loading)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01 (Arquitectura en capas y UoW asincrónico)

---

## FASE 3 — Seguridad, Autenticación y Autorización Dinámica

### [C-04] `auth-and-passwords`
- **Estado**: `[ ]` pendiente
- **Scope**: Autenticación segura, contraseñas con bcrypt en hilo separado, mitigación de timing attacks, rate limiting y cookies HttpOnly
  - Módulo `app/core/security.py`:
    - Hashing y verificación con `bcrypt` desacoplados del bucle de eventos mediante `asyncio.to_thread`
    - Control de saturación de CPU con semáforo asincrónico `asyncio.Semaphore(value=settings.BCRYPT_MAX_CONCURRENCY)` y costo configurable `settings.BCRYPT_ROUNDS`
    - Precalculo de hash ficticio en memoria al arranque para mitigación de timing attacks (RN-09)
    - Emisión y validación de tokens JWT (`HS256`, `sub=str(user.id)`, `exp`, claim `iat` con precisión de microsegundos en flotante sin truncar a enteros, y roles informativos)
    - Utilidad para setear cookie `access_token` (`HttpOnly`, `SameSite=Lax`, `Max-Age=settings.JWT_EXPIRATION_SECONDS`, directiva `Secure=settings.COOKIE_SECURE`) y utilidad para eliminar cookie en logout
  - Esquemas DTO en `app/modules/usuarios/schemas.py`:
    - `RegistroClienteRequest`: email, password (longitud máxima 72 bytes, rechaza más largos con 422), nombre, documento, teléfono (`extra="forbid"`)
    - `LoginRequest`: email, password (máx 72 bytes) (`extra="forbid"`)
    - `CambiarPasswordRequest`: password_actual, password_nueva (`extra="forbid"`)
    - `LoginResponse`: `mensaje`, `debe_cambiar_password`, `expira_en_segundos` (sin exponer JWT en el cuerpo JSON)
    - `UsuarioResponse`: id, email, nombre, activo, debe_cambiar_password (sin exponer `password_hash`)
  - Lógica de servicio y UoW en `app/modules/usuarios/`:
    - `POST /auth/registro`: Hashea contraseña antes de abrir la transacción; en un único bloque de UoW crea `usuario`, asigna rol `CLIENTE` y crea `cliente`. Si el documento o email ya existen, o falla cualquier paso, rollback atómico y responde HTTP 409 Conflict (RN-02)
    - `POST /auth/login`: Valida 5 intentos fallidos consecutivos en 60s en `intento_acceso` para el par email+IP (responde 429 con `Retry-After: 60` sin verificar bcrypt). Si usuario no existe, corre verificación contra hash ficticio (RN-09). Si contraseña es inválida, registra intento fallido en sesión independiente con commit inmediato y responde 401. Si es válida, registra intento exitoso, resetea ventana, emite cookie `access_token` y responde 200 (RN-08)
    - `POST /auth/logout`: Invalida cookie en el cliente HTTP (`Max-Age=0`)
    - `GET /auth/yo`: Responde datos del usuario autenticado a partir de la cookie de sesión
    - `POST /auth/cambiar-password`: Valida password actual, hashea la nueva, actualiza `password_cambiada_en = datetime.now(timezone.utc)` y `debe_cambiar_password = False`. Emite nueva cookie; las sesiones anteriores con `iat < password_cambiada_en` quedan invalidadas de inmediato con 401 (RN-07)
  - Montaje de rutas en `app/modules/usuarios/router.py` en el grupo abierto de `main.py`
  - Tests: Validación de casos de prueba C-03 (auto-registro), C-04 (login exitoso con cookie), C-05 (timing attacks), C-06 (rate limiting 429), C-07 (debe_cambiar_password) y C-08 (invalidación de sesiones con microsegundos)
- **Dependencias**: C-03
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §Flujo de Cambio Obligatorio de Contraseña
  - `knowledge-base/05_reglas_de_negocio.md` §RN-02 (Auto-registro), §RN-06, §RN-07 (Cambio clave e invalidación), §RN-08 (Rate limit), §RN-09 (Timing attack)
  - `knowledge-base/06_funcionalidades.md` §US-002, US-003, US-004
  - `knowledge-base/07_flujos_principales.md` §Flujo 1 (Login), §Flujo 2 (Auto-registro), §Flujo 4 (Cambio de contraseña)
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad y Sesión independiente

---

### [C-05] `rbac-authorization-and-isolation`
- **Estado**: `[ ]` pendiente
- **Scope**: Dependencias de autorización FastAPI con consulta a base de datos en tiempo real, gestión de personal, autoprotección de ADMIN y aislamiento de clientes
  - Dependencias de seguridad en `app/core/dependencies.py`:
    - Inyector `get_current_user`: Lee cookie `access_token` (rechaza `Authorization: Bearer`), decodifica JWT, consulta usuario activo en DB y valida `iat >= user.password_cambiada_en` (401 si expiró o fue invalidado)
    - Middleware o filtro de grupo protegido: Si `current_user.debe_cambiar_password == True`, aborta con HTTP 403 Forbidden para cualquier ruta del grupo protegido (RN-06)
    - Inyector `require_roles(*roles_permitidos)`: Consulta en PostgreSQL sobre la tabla `asignacion_rol` en tiempo real en cada petición (`vence_en IS NULL OR vence_en > NOW()` y `revocada_en IS NULL`). Si el usuario no tiene al menos un rol vigente permitido, responde HTTP 403 Forbidden (RN-04)
    - Inyector `get_current_cliente`: Resuelve la entidad `Cliente` vinculada al `current_user` para garantizar el aislamiento estricto en rutas `/mis-*` (RN-17)
  - Administración de personal y roles en `app/modules/usuarios/`:
    - `POST /usuarios`: Alta de personal operativo/administrativo por ADMIN con password provisoria (`debe_cambiar_password = True`), validación de email único (409)
    - `GET /usuarios/{id}/roles`: Consulta de asignaciones históricas y vigentes de un usuario
    - `POST /usuarios/{id}/roles`: Asignación de rol (`ADMIN`, `RECEPCION`, `MECANICO`) con fecha `vence_en` opcional (validación: debe estar en el futuro y con timezone UTC; si es en el pasado o sin timezone responde 422). Si ya posee asignación abierta para ese rol, responde 409 (RN-03)
    - `DELETE /usuarios/{id}/roles/{rol}`: Revocación lógica (`revocada_en = NOW()`). Regla de autoprotección RN-05: Un administrador no puede revocarse a sí mismo el rol `ADMIN` (409) y el sistema no puede quedar sin administradores activos vigentes (409)
    - `GET /eventos`: Consulta paginada de registros en `evento_seguridad` accesible solo para rol `ADMIN`
  - Tests: Validación de casos de prueba C-09 (RBAC dinámico en DB), C-10 (autoprotección de ADMIN) y C-11 (aislamiento de clientes)
- **Dependencias**: C-04
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §Modelo de Roles Dinámicos en Base de Datos y Matriz RBAC
  - `knowledge-base/05_reglas_de_negocio.md` §RN-03 (Asignación única), §RN-04 (Consulta roles en tiempo real), §RN-05 (Autoprotección ADMIN), §RN-17 (Aislamiento clientes)
  - `knowledge-base/06_funcionalidades.md` §US-005 (Asignación y revocación dinámica)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-02 (Cookies HttpOnly), §DD-03 (RBAC dinámico en DB)

---

## FASE 4 — Dominio Operativo: Clientes, Vehículos y Repuestos

> Los changes C-06 y C-07 pueden implementarse en paralelo una vez archivado C-05. Ambos deben estar completos antes de iniciar C-08.

### [C-06] `clientes-and-vehiculos`
- **Estado**: `[ ]` pendiente
- **Scope**: Módulo de clientes y vehículos con soft delete, reasignación por venta y validación de órdenes abiertas
  - Módulo `app/modules/clientes/schemas.py`:
    - `CrearClienteRequest`: nombre, documento, teléfono (`extra="forbid"`)
    - `ClienteResponse`: id, usuario_id, nombre, documento, teléfono
    - `CrearVehiculoRequest`: patente, marca, modelo, anio (validación Pydantic `1950 <= anio <= 2100`) (`extra="forbid"`)
    - `VehiculoResponse`: id, cliente_id, patente, marca, modelo, anio
  - Persistencia en `app/modules/clientes/repository.py` y `unit_of_work.py`:
    - `ClienteRepository(BaseRepository[Cliente])`: Métodos para búsqueda por documento, búsqueda por `usuario_id` y precarga de vehículos
    - `VehiculoRepository(SoftDeleteRepository[Vehiculo])`: Búsqueda por patente activa (`borrado_en IS NULL`) y listado por cliente
    - `ClientesUnitOfWork`: Gestor de contexto para operaciones del módulo
  - Servicios y rutas en `app/modules/clientes/`:
    - `POST /clientes`: Alta de cliente sin cuenta web por `RECEPCION` o `ADMIN`; documento único en todo el sistema (409 ante colisión)
    - `GET /clientes/{id}`: Detalle de cliente con flota de vehículos activos asociados (404 si no existe)
    - `POST /clientes/{id}/vehiculos`: Registro de vehículo asociado al cliente. Unicidad de patente aplicada exclusivamente entre vehículos vigentes (`WHERE borrado_en IS NULL`). Si un vehículo fue dado de baja previamente, permite registrar la misma patente para un nuevo cliente por venta (RN-01)
    - `DELETE /vehiculos/{id}`: Borrado lógico (`borrado_en = NOW()`). Verificación de negocio RN-16: Si el vehículo tiene órdenes de trabajo abiertas (aquellas en catálogo sin `es_final = True`), rechaza con HTTP 409 Conflict
    - `GET /mis-vehiculos`: Ruta protegida para clientes autenticados (`rol = CLIENTE`) que filtra estrictamente por el `cliente_id` del usuario en sesión (RN-17)
  - Montaje de rutas en `app/modules/clientes/router.py` en el grupo protegido
  - Tests: Validación de casos de prueba C-12 (CRUD clientes y vehículos, validación de año, re-alta de patente vendida) y C-13 (bloqueo de baja con órdenes abiertas)
- **Dependencias**: C-05
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §cliente, §vehiculo
  - `knowledge-base/05_reglas_de_negocio.md` §RN-01 (Unicidad y venta), §RN-16 (Conservación y bloqueo de baja), §RN-17 (Aislamiento)
  - `knowledge-base/06_funcionalidades.md` §US-006 (Gestión clientes/vehículos), §US-007 (Autoservicio)
  - `knowledge-base/08_arquitectura_propuesta.md` §clientes

---

### [C-07] `repuestos-and-inventario`
- **Estado**: `[ ]` pendiente
- **Scope**: Módulo de repuestos, inventario con movimientos atómicos, prohibición de stock en PATCH y trazabilidad histórica de precios
  - Módulo `app/modules/repuestos/schemas.py`:
    - `CrearRepuestoRequest`: codigo, descripcion, precio (`Decimal > 0`), stock_inicial (`int >= 0`) (`extra="forbid"`)
    - `ActualizarRepuestoRequest`: descripcion opcional, precio opcional (`Decimal > 0`). El campo `stock` está estrictamente ausente del contrato; cualquier envío de `stock` en el payload rechaza con HTTP 422 (RN-14)
    - `ReponerStockRequest`: cantidad (`int > 0`), motivo (`extra="forbid"`)
    - `RepuestoResponse`: id, codigo, descripcion, precio, stock
    - `MovimientoStockResponse`: id, repuesto_id, orden_id, usuario_id, cantidad, motivo, cuando
    - `HistorialPrecioResponse`: id, repuesto_id, usuario_id, precio_anterior, precio_nuevo, cuando
  - Persistencia en `app/modules/repuestos/repository.py` y `unit_of_work.py`:
    - `RepuestoRepository(SoftDeleteRepository[Repuesto])`: Búsqueda por código activo (`borrado_en IS NULL`)
    - `MovimientoStockRepository(BaseRepository[MovimientoStock])`
    - `HistorialPrecioRepuestoRepository(BaseRepository[HistorialPrecioRepuesto])`
    - `RepuestosUnitOfWork`: Coordina transacciones de stock y precios
  - Servicios y rutas en `app/modules/repuestos/`:
    - `GET /repuestos` y `GET /repuestos/{id}`: Consulta con paginación estándar para personal del taller (`ADMIN`, `RECEPCION`, `MECANICO`)
    - `POST /repuestos`: Alta por `ADMIN`. En la misma transacción: inserta `repuesto` y asienta movimiento en `movimiento_stock` con `cantidad = stock_inicial` y `motivo = "Stock inicial"` (RN-14). Código único entre vigentes (409)
    - `PATCH /repuestos/{id}`: Modificación de repuesto por `ADMIN`. Si el precio enviado difiere del precio actual, inserta fila en `historial_precio_repuesto` en la misma transacción (RN-20). Si el precio es idéntico o no se envía, no genera fila histórica. Rechaza con 422 si se intenta modificar stock (RN-14)
    - `POST /repuestos/{id}/reponer`: Reposición manual de stock por `ADMIN`. Incrementa `repuesto.stock` y registra fila en `movimiento_stock`
    - `DELETE /repuestos/{id}`: Borrado lógico (`borrado_en = NOW()`) por `ADMIN`
    - `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios`: Auditoría histórica para `ADMIN`
  - Tests: Validación de casos de prueba C-14 (triggers de sólo agregado en PostgreSQL), C-15 (alta, reposición y rechazo de stock en PATCH) y C-16 (trazabilidad obligatoria de cambios de precio)
- **Dependencias**: C-05
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §repuesto, §movimiento_stock, §historial_precio_repuesto
  - `knowledge-base/05_reglas_de_negocio.md` §RN-01 (Unicidad código), §RN-14 (Mutación stock solo por movimientos), §RN-15 (Sólo agregado), §RN-20 (Historial de precios)
  - `knowledge-base/06_funcionalidades.md` §US-008 (Inventario), §US-012 (Sólo agregado)
  - `knowledge-base/08_arquitectura_propuesta.md` §repuestos

---

## FASE 5 — Dominio de Órdenes de Trabajo y Notificaciones

### [C-08] `ordenes-and-background-tasks`
- **Estado**: `[ ]` pendiente
- **Scope**: Módulo de órdenes de trabajo, catálogo de estados inmutable, composición atómica, transiciones de estado, descuento de inventario en UoW y BackgroundTasks
  - Módulo `app/modules/ordenes/schemas.py`:
    - `ItemOrdenInput`: repuesto_id, cantidad (`int > 0`) (`extra="forbid"`, sin precios)
    - `CrearOrdenRequest`: vehiculo_id, falla, items (`list[ItemOrdenInput]` de longitud >= 1) (`extra="forbid"`, sin totales ni precios)
    - `ItemOrdenResponse`: id, repuesto_id, cantidad, precio_unitario, subtotal
    - `OrdenTrabajoResponse`: id, vehiculo_id, mecanico_id, estado, falla, creada_en, total, items
    - `EstadoOrdenResponse`: codigo, descripcion, posicion, es_final
  - Persistencia en `app/modules/ordenes/repository.py` y `unit_of_work.py`:
    - `EstadoOrdenRepository(ReadOnlyRepository[EstadoOrden])`: Catálogo inmutable desde la API (RN-19)
    - `OrdenTrabajoRepository(BaseRepository[OrdenTrabajo])`: Consultas con precarga obligatoria `selectinload` de `items`, repuestos asociados y vehículo
    - `ItemOrdenRepository`, `HistorialEstadoOrdenRepository`
    - `OrdenesUnitOfWork`: Coordina transacciones complejas integrando órdenes, ítems, repuestos y auditoría
  - Servicios y rutas en `app/modules/ordenes/`:
    - `GET /estados-orden`: Consulta del catálogo ordenado por `posicion`
    - `POST /ordenes`: Creación de orden por `RECEPCION` o `ADMIN`. Valida: estado inicial `PENDIENTE`, al menos 1 ítem, sin repuestos repetidos (RN-10), vehículo no borrado y repuestos vigentes. Copia los precios unitarios de cada repuesto en ese instante y calcula el total en el servidor. Inserta fila inicial en `historial_estado_orden` (`desde_estado = None`, `hasta_estado = "PENDIENTE"`). Si la tabla `estado_orden` está vacía, responde 409 con mensaje explicativo (RN-19)
    - `GET /ordenes` y `GET /ordenes/{id}`: Consulta con RBAC. Personal del taller ve todas; rol `CLIENTE` solo puede ver órdenes de sus propios vehículos (403 si pertenece a otro)
    - `POST /ordenes/{id}/iniciar`: Mecánico inicia orden pendiente; pasa a `EN_REPARACION`, se le asigna `mecanico_id` e inserta fila en `historial_estado_orden` (RN-11)
    - `POST /ordenes/{id}/terminar`: Mecánico asignado o `ADMIN` finaliza la orden. En una única transacción de UoW: valida `EN_REPARACION` (o 409), verifica que haya stock suficiente para todos los ítems (`repuesto.stock >= item.cantidad`). Si no alcanza, lanza excepción, UoW hace rollback total sin escrituras y responde 409 (RN-13). Si hay stock, descuenta `repuesto.stock`, inserta filas en `movimiento_stock` (cantidad negativa, motivo), pasa a `TERMINADA` e inserta en `historial_estado_orden`. Tras el commit exitoso, encola simulación de aviso al cliente con `BackgroundTasks` (`asyncio.sleep(0.5)`)
    - `POST /ordenes/{id}/cancelar`: Cancelación desde `PENDIENTE`. Permisos autorizados: RECEPCION, ADMIN o CLIENTE dueño del vehículo. Precedencia: valida permisos de identidad antes que el estado (403 antes que 409) (RN-12)
    - `GET /mis-ordenes`: Autoservicio para rol `CLIENTE` restringido a órdenes de sus propios vehículos (RN-17)
  - Tests: Validación de casos de prueba C-17 (creación y cálculo servidor), C-18 (transición de estados, consumo atómico y rollback por falta de stock) y C-19 (cancelación y orden de evaluación 403 vs 409)
- **Dependencias**: C-06, C-07
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §estado_orden, §orden_trabajo, §item_orden, §historial_estado_orden
  - `knowledge-base/05_reglas_de_negocio.md` §RN-10 (Creación y cálculo), §RN-11 (Máquina de estados), §RN-12 (Cancelación y precedencia), §RN-13 (Consumo atómico stock), §RN-19 (Catálogo inmutable)
  - `knowledge-base/06_funcionalidades.md` §US-009, US-010, US-011
  - `knowledge-base/07_flujos_principales.md` §Flujo 3 (Ciclo de Vida de una Orden y Terminar Orden)
  - `knowledge-base/08_arquitectura_propuesta.md` §ordenes

---

## FASE 6 — Poblado Canónico y Verificación E2E

### [C-09] `seed-and-test-suite`
- **Estado**: `[ ]` pendiente
- **Scope**: Script canónico `seed.py`, suite de pruebas `.http` interactivas en `test/`, script SQL de triggers y validación integral de casos C-01 a C-19
  - Script canónico de datos `seed.py`:
    - Script independiente ejecutable (`python seed.py`) que limpia tablas y puebla de forma reproducible la base de datos para los casos de prueba oficiales
    - Catálogo `estado_orden`: `PENDIENTE` (pos 1), `EN_REPARACION` (pos 2), `TERMINADA` (pos 3, es_final=True), `CANCELADA` (pos 4, es_final=True)
    - Usuarios y roles: `admin@example.com` (ADMIN), `admin2@example.com` (ADMIN), `recepcion@example.com` (RECEPCION), `mecanico@example.com` (MECANICO), `mecanico2@example.com` (MECANICO), `cliente@example.com` (CLIENTE), `nuevo@example.com` (MECANICO con `debe_cambiar_password = True`)
    - Clientes y flota: Laura (asociada a `cliente@example.com`) con 2 vehículos (`AC456EF` y otro), Jorge (sin usuario) con 1 vehículo
    - Repuestos canónicos: Filtro de aceite (8500.00, stock 10), Pastillas de freno (32000.00, stock 4), Bujía (precio estándar, stock 2), Aceite por litro (12000.00, stock 20) con movimientos iniciales
    - Órdenes canónicas: Orden 1 (`PENDIENTE`, vehículo de Laura), Orden 2 (`EN_REPARACION`, vehículo de Jorge, asignada a `mecanico@example.com`, con 4 bujías para verificar rechazo por falta de stock)
    - Historial de precio inicial (filtro de 8000 a 8500) y evento de seguridad inicial con actor `SISTEMA` ("Carga de los datos iniciales")
  - Script de validación de triggers `test/solo_agregado.sql`:
    - 6 sentencias SQL directas (`UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`) ejecutadas con `psql` para comprobar que los disparadores PL/pgSQL abortan la operación con error (Caso oficial C-14 / RN-15)
  - Suite interactiva de pruebas HTTP en `test/*.http`:
    - `01_health.http`: Casos C-01 (`GET /health/live`) y C-02 (`GET /health/ready`)
    - `02_auth.http`: Casos C-03 (auto-registro atómico y conflicto 409), C-04 (login exitoso con Set-Cookie HttpOnly), C-05 (timing attacks y dummy hash), C-06 (rate limiting 429 con Retry-After), C-07 (debe_cambiar_password y 403 en grupo protegido), C-08 (invalidación de sesiones previas comparando `iat` con microsegundos)
    - `03_roles.http`: Casos C-09 (RBAC dinámico en DB y expiración de roles) y C-10 (autoprotección de ADMIN: auto-revocación 409 y último admin 409)
    - `04_clientes_vehiculos.http`: Casos C-11 (aislamiento de clientes en `/mis-vehiculos`), C-12 (CRUD clientes y vehículos, validación año 1950..2100 y re-alta de patente vendida), C-13 (bloqueo de baja con órdenes abiertas)
    - `05_repuestos.http`: Casos C-15 (alta, reposición de stock y rechazo de campo `stock` en PATCH con 422) y C-16 (trazabilidad obligatoria de cambios de precio en `historial_precio_repuesto`)
    - `06_ordenes.http`: Casos C-17 (creación, copiado de precios y cálculo de total en servidor), C-18 (transición de estados, consumo atómico de stock y rollback total ante stock insuficiente) y C-19 (cancelación y precedencia de validación 403 antes que 409)
  - Documentación de pruebas y verificación E2E en `test/README.md`
- **Dependencias**: C-08
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Seed Data Inicial (`seed.py`)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-01 a RN-20
  - `knowledge-base/07_flujos_principales.md` §Flujos 1, 2, 3 y 4
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura Obligatoria de Directorios
