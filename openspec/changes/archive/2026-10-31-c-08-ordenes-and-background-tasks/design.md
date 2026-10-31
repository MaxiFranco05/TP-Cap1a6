# Design: Órdenes de Trabajo y Background Tasks (C-08)

## Context

Este cambio implementa el módulo operativo principal de la API del taller mecánico. La aplicación ya cuenta con persistencia relacional (`SQLModel`, `asyncpg`, `Alembic`), abstracción transaccional (`BaseRepository`, `SoftDeleteRepository`, `ReadOnlyRepository`, `UnitOfWork`), autenticación (`cookies HttpOnly`, `bcrypt` en thread pool) y control de accesos (`require_roles` y aislamiento con `get_current_cliente`).

La consigna oficial establece restricciones específicas para el ciclo de vida de órdenes:
- Composición atómica: una orden nace con sus ítems (RN-10).
- Transición estricta de estados y máquina de estados (RN-11).
- Cancelación con precedencia de autorización sobre validación de estado (RN-12).
- Terminación transaccional con descuento atómico de stock y rollback total ante faltantes (RN-13 y RN-14).
- Inmutabilidad de catálogos e históricos (RN-15 y RN-19).
- Consultas fijas sin problema N+1 (Caso C-15) y aviso simulado en segundo plano con `BackgroundTasks` (sección 3.9).

## Goals / Non-Goals

**Goals:**
- Implementar los esquemas DTO con contratos estrictos (`extra="forbid"`), garantizando que precios y totales nunca viajen en el cuerpo de creación.
- Construir `OrdenesUnitOfWork` que agrupe repositorios de órdenes, ítems, historial, repuestos y movimientos de stock.
- Implementar `OrdenesService` con toda la lógica de negocio y transiciones de estado.
- Resolver la precedencia estricta de validación en cancelaciones (HTTP 403 antes que 409).
- Implementar la precarga anticipada (`selectinload`) en `OrdenTrabajoRepository` para cumplir con lecturas constantes en tiempo y consultas fijas (sin N+1).
- Integrar `BackgroundTasks` para simular la notificación al cliente tras confirmar la terminación de una orden.

**Non-Goals:**
- Modificar el esquema de la base de datos (las tablas `orden_trabajo`, `item_orden`, `historial_estado_orden` y `estado_orden` ya fueron creadas en C-02).
- Implementar colas distribuidas o brokers con Redis/Celery (la consigna explicita que queda para el Capítulo 8).
- Gestionar concurrencia con bloqueos pesimistas (`SELECT FOR UPDATE`) para evitar lost updates (la consigna indica que queda para el Capítulo 7).

## Decisions

### 1. Repositorio de catálogo inmutable (`EstadoOrdenRepository`)
- **Decisión**: Extender de `ReadOnlyRepository[EstadoOrden]`.
- **Razón**: El catálogo `estado_orden` tiene clave primaria textual (`codigo`), y la consigna (RN-19) prohíbe explícitamente editarlo desde la API. Extender de `BaseRepository` expondría métodos de escritura `add()`, `update()`, `delete()` que no deben existir. Si al intentar crear una orden la tabla está vacía, el servicio responde HTTP 409 con mensaje propio.
- **Alternativas consideradas**: Heredar de `BaseRepository` y sobreescribir métodos con excepciones (antipatrón de Liskov Substitution Principle).

### 2. Coordinación transaccional con `OrdenesUnitOfWork`
- **Decisión**: Un `UnitOfWork` dedicado para el módulo de órdenes que encapsula la sesión y compone:
  - `ordenes`: `OrdenTrabajoRepository`
  - `items`: `ItemOrdenRepository`
  - `historial`: `HistorialEstadoOrdenRepository`
  - `estados`: `EstadoOrdenRepository`
  - `repuestos`: `RepuestoRepository`
  - `movimientos`: `MovimientoStockRepository`
  - `vehiculos`: `VehiculoRepository`
- **Razón**: La terminación de una orden (RN-13) requiere leer la orden, verificar stock en múltiples filas de `repuesto`, descontar stock, crear filas en `movimiento_stock`, actualizar la orden a `TERMINADA` y registrar el historial. Si un solo repuesto no alcanza, la excepción de dominio lanzada por el servicio provoca que el UoW ejecute `await session.rollback()` automático, dejando la base intacta.
- **Alternativas consideradas**: Usar repositorios sueltos en el servicio haciendo `flush()` o `commit()` manuales (violaría la regla dura 3 de la arquitectura).

### 3. Precedencia de permisos en cancelación (`POST /ordenes/{id}/cancelar`)
- **Decisión**: No usar dependencia estática `require_roles("RECEPCION", "ADMIN")` en la ruta. En su lugar, inyectar el usuario autenticado (`get_current_user`) y cliente opcional (`get_current_cliente`), delegando la verificación al servicio:
  1. Si el usuario no tiene rol `ADMIN` ni `RECEPCION`, y no es el cliente dueño del vehículo asociado a la orden (`orden.vehiculo.cliente_id != current_cliente.id`), lanzar HTTP 403 Forbidden.
  2. Una vez confirmada la legitimidad del actor, validar si la orden se encuentra en estado `PENDIENTE`. Si no lo está, lanzar HTTP 409 Conflict.
- **Razón**: Permite cumplir estrictamente la regla de precedencia de la consigna: un cliente que intenta cancelar una orden que no le pertenece debe recibir siempre 403, incluso si la orden ya estuviera terminada o cancelada.

### 4. Precarga anticipada estricta (`selectinload`)
- **Decisión**: En `OrdenTrabajoRepository.get_detalle(id)` y métodos de consulta, aplicar:
  ```python
  select(OrdenTrabajo).options(
      selectinload(OrdenTrabajo.vehiculo).selectinload(Vehiculo.cliente),
      selectinload(OrdenTrabajo.items).selectinload(ItemOrden.repuesto),
      selectinload(OrdenTrabajo.historial)
  )
  ```
- **Razón**: Garantiza un número constante y fijo de sentencias SQL emitidas a PostgreSQL independientemente de la cantidad de ítems que contenga la orden, superando la prueba del Caso C-15.

### 5. Notificación al cliente con `BackgroundTasks`
- **Decisión**: Pasar la instancia de `BackgroundTasks` de FastAPI al servicio o programar la corutina `notificar_cliente_orden_terminada(orden_id, cliente_email)` en el router inmediatamente después de que el bloque `async with uow:` confirme exitosamente la transacción.
- **Razón**: Asegura que el aviso nunca se dispare si la transacción aborta por falta de stock (RN-13) y corre de forma no bloqueante después de que la respuesta HTTP ya fue enviada al cliente.

## UI Mockups

Decision: no (no UI)

## Risks / Trade-offs

- **[Riesgo] Triggers de solo agregado en PostgreSQL rechazan mutaciones** → **Mitigación**: `HistorialEstadoOrden` y `MovimientoStock` solo reciben operaciones `INSERT`. Nunca se intenta actualizar ni borrar una fila existente.
- **[Riesgo] Inconsistencia si falla el aviso en segundo plano** → **Mitigación**: La consigna establece que el aviso es simulado y su eventual pérdida en memoria no invalida la persistencia de la orden ni compromete el estado de la base de datos.
- **[Riesgo] Concurrencia de stock en terminaciones simultáneas** → **Mitigación**: Documentado en la sección "Qué queda afuera" de la consigna oficial (lost updates tolerados en esta etapa; CHECK `stock >= 0` previene stocks negativos).
