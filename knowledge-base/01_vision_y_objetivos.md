# Visión y Objetivos

## Propósito del sistema

API REST asincrónica y robusta para la gestión diaria de un taller mecánico automotriz, desarrollada para la materia Programación III (UTN) bajo el eje "Unidad 1 a 6: Del Objeto a la Transacción". El sistema centraliza la administración de clientes, vehículos, órdenes de trabajo con estados transitables, control e inventario de repuestos, y gestión de personal con autorización RBAC en base de datos y autoservicio web para clientes.

El núcleo del sistema prioriza la consistencia transaccional garantizada por la base de datos y el patrón Unit of Work, asegurando que ninguna operación parcial corrompa datos, y blindando la seguridad con autenticación mediante cookies `HttpOnly`, contraseñas con bcrypt fuera del bucle de eventos, y disparadores de sólo agregado en PostgreSQL.

---

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|---|---|---|
| **ADMIN** | Mantener el control integral y seguridad operativa del taller. | - Gestionar personal y asignar/revocar roles con vigencia.<br>- Mantener catálogo de repuestos, precios y reponer stock.<br>- Auditar eventos de seguridad y transiciones de órdenes.<br>- Cancelar o terminar órdenes en situaciones excepcionales. |
| **RECEPCION** | Agilizar el ingreso y atención de clientes y vehículos. | - Registrar clientes y vincular sus vehículos.<br>- Crear órdenes de trabajo asociando fallas y repuestos requeridos.<br>- Consultar catálogo y stock de repuestos.<br>- Cancelar órdenes pendientes a solicitud del cliente o administrativa. |
| **MECANICO** | Ejecutar reparaciones con trazabilidad de insumos. | - Visualizar órdenes pendientes y tomarlas (pasándolas a `EN_REPARACION`).<br>- Concluir reparaciones (`TERMINADA`) registrando de forma atómica el consumo de repuestos y movimientos de stock. |
| **CLIENTE** | Autoservicio web transparente y seguro. | - Auto-registrarse en la plataforma.<br>- Consultar el estado de sus vehículos registrados (`/mis-vehiculos`).<br>- Dar seguimiento a sus órdenes de reparación (`/mis-ordenes`).<br>- Cancelar sus propias órdenes pendientes. |
| **SISTEMA** | Garantizar trazabilidad e integridad técnica. | - Registrar eventos de auditoría y carga inicial (`seed.py`).<br>- Proteger tablas inmutables mediante disparadores en base de datos. |

---

## Alcance v1.0 (Capítulos 1 a 6 de la Cátedra)

1. **Fundamentos y ciclo de vida (Capítulo 1)**:
   - Configuración desacoplada en clase `Settings` con `pydantic-settings` (sin secretos por defecto).
   - Lifespan ASGI para creación de motor asincrónico, pool dimensionado y fábrica de sesiones en `app.state`.
   - Cierre ordenado del motor con `dispose()`.
   - Endpoints `/health/live` (sin tocar DB) y `/health/ready` (ejecuta `SELECT 1` con respuesta 503 en fallo).
2. **Contratos y CRUD (Capítulo 2)**:
   - DTOs/Schemas Pydantic independientes de los modelos de tabla.
   - Contratos con `extra="forbid"` y rechazo de campos no solicitados.
   - Operaciones PATCH con `exclude_unset=True`.
   - Formato estándar de paginación `{items, total, page, size, pages}` con validación de límites (size 1..100, page válida o 422).
   - Tipos numéricos precisos: `Decimal` en Python y `NUMERIC` en PostgreSQL para dinero.
3. **Ejecución asincrónica sin bloqueos (Capítulo 3)**:
   - Todos los handlers con `async def`.
   - Operaciones CPU-bound de bcrypt ejecutadas en subprocesos con `asyncio.to_thread` bajo un semáforo de concurrencia.
   - Carga perezosa (lazy loading) estrictamente evitada; todas las relaciones se precargan en el repositorio.
   - Simulación de aviso asincrónico al cliente tras terminar orden mediante `BackgroundTasks` (`asyncio.sleep(0.5)`).
4. **Persistencia relacional y migraciones (Capítulo 4)**:
   - Modelos SQLModel / SQLAlchemy con relaciones compuestas, asociaciones y uno a uno opcional.
   - Catálogo `estado_orden` tipado por clave foránea y enum en código.
   - Borrado lógico con índices únicos parciales (`WHERE borrado_en IS NULL`) en patente y código de repuesto.
   - Migraciones con Alembic plantilla asincrónica (dos entregas: 1 autogenerada con tablas e índices, 1 manual con triggers).
5. **Autenticación y autorización (Capítulo 5)**:
   - Hash de contraseñas con bcrypt (costo configurable, límite estricto de 72 bytes).
   - Login con mitigación de timing attack mediante hash ficticio y rate limiting (5 fallos en 60s en tabla `intento_acceso`).
   - Token JWT transportado exclusivamente en cookie `HttpOnly` (`SameSite=Lax`, configurable `Secure`).
   - Flujo de cambio obligatorio de contraseña (`debe_cambiar_password`) con separación de rutas abiertas vs protegidas.
   - Autorización consultando roles vigentes en PostgreSQL en cada petición protegida.
   - Distinción rigurosa de errores 401 (no autenticado) vs 403 (no autorizado).
6. **Repositorios, Unit of Work y transacciones (Capítulo 6)**:
   - Jerarquía de repositorios `BaseRepository[T]` y `SoftDeleteRepository[T]`.
   - Repositorio de catálogo exclusivo de solo lectura.
   - Métodos de repositorio usan `flush()`, nunca `commit()`.
   - `UnitOfWork` base como gestor de contexto asincrónico que controla `commit()` y `rollback()`.
   - Transacciones atómicas complejas: auto-registro (usuario + rol + cliente), terminación de orden (orden + ítems + movimientos + stock + historial) y actualización de precios.
   - Disparador en base de datos para garantizar sólo agregado en `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`.
   - `seed.py` para reinicio y carga de datos iniciales requeridos por la suite de pruebas.

---

## Fuera de alcance (Explícito por Cátedra)

- **Control de concurrencia pesimista/optimista en stock (Capítulo 7)**:
  Se asume y tolera que dos órdenes concurrentes que terminen al mismo tiempo puedan generar una actualización perdida de stock sin superar las validaciones de CHECK.
- **Colas de mensajería distribuidas con Redis/Celery (Capítulo 8)**:
  El aviso al cliente se despacha en proceso mediante `BackgroundTasks`. Se asume que el reinicio del servidor podría perder avisos pendientes en memoria.
- **Frontend web y aplicaciones móviles**:
  El proyecto implementa exclusivamente la API REST backend y se verifica contra los 19 casos de prueba `.http` y scripts `.sql`.

---

## Métricas de éxito

1. **Aprobación de la suite de pruebas**: 100% de los casos de prueba de referencia (C-01 a C-19) pasan con los códigos y respuestas esperadas.
2. **Integridad referencial y transaccional**: Cero registros inconsistentes o huérfanos ante fallos de validación o rollback.
3. **Cero respuestas 500 no controladas**: Todas las entradas inválidas o colisiones son interceptadas y devuelven 400, 401, 403, 404, 409, 422 o 429.
4. **Cumplimiento de arquitectura por capas**: Código estrictamente segregado sin dependencias cruzadas (Router → Service → UoW → Repository → Model).
