# Proposal: Órdenes de Trabajo y Background Tasks (C-08)

## Why

El taller mecánico necesita orquestar el ciclo operativo central del negocio: apertura de órdenes de trabajo para vehículos ingresados, asociación de fallas y repuestos requeridos, seguimiento del flujo de reparación mediante una máquina de estados estricta y terminación transaccional con descuento automático de stock y aviso asincrónico al cliente.

Hasta ahora el sistema cuenta con autenticación, RBAC, gestión de clientes, vehículos y catálogo de repuestos. Este cambio implementa el dominio de órdenes de trabajo conectando todos estos subsistemas bajo un `UnitOfWork` transaccional que asegura consistencia absoluta (evitando órdenes a medio crear o descuentos de inventario inconsistentes si el stock es insuficiente).

## What Changes

- **Catálogo inmutable de estados (`estado_orden`)**:
  - Exposición de `GET /estados-orden` ordenado por `posicion` para usuarios autenticados.
  - Implementación de `EstadoOrdenRepository` heredando de `ReadOnlyRepository[EstadoOrden]`, impidiendo modificaciones desde la API (RN-19).
  - Validación de catálogo poblado: Si la tabla `estado_orden` no tiene registros cargados, responder HTTP 409 con mensaje explicativo ante cualquier intento de creación de orden (RN-19).

- **Contratos DTO estrictos (`extra="forbid"`)**:
  - `ItemOrdenInput`: `repuesto_id`, `cantidad` (`int > 0`). Precios y subtotales nunca viajan en el payload (RN-10).
  - `CrearOrdenRequest`: `vehiculo_id`, `falla`, `items: list[ItemOrdenInput]` (mínimo 1 ítem, sin repuestos repetidos) (RN-10). Totales y estados nunca viajan en el request.
  - `ItemOrdenDetalleResponse`: `repuesto_id`, `codigo`, `descripcion`, `cantidad`, `precio_unitario`, `subtotal`.
  - `HistorialEstadoOrdenResponse`: `desde_estado`, `hasta_estado`, `usuario_id`, `cuando`.
  - `OrdenTrabajoDetalleResponse`: `id`, `estado`, `patente`, `total`, `creada_en`, `mecanico_id`, `falla`, `cliente`, `items`, `historial`.
  - `OrdenTrabajoResumenResponse`: Contrato ligero para listados paginados.

- **Alta y composición de órdenes (`POST /ordenes`)**:
  - Restringido a roles `RECEPCION` y `ADMIN`.
  - Creación atómica: valida que el vehículo exista y no esté dado de baja; verifica que los repuestos existan y no estén dados de baja. Copia los precios unitarios vigentes de cada repuesto, calcula subtotales y total general en el servidor (RN-10).
  - Inserta la orden en estado `PENDIENTE`, sus ítems y el primer registro de auditoría en `historial_estado_orden` (`desde_estado = None`, `hasta_estado = "PENDIENTE"`), todo dentro de la misma transacción (201 Created).

- **Consultas y detalle con precarga Eager Loading (evitando N+1)**:
  - `GET /ordenes`: Listado paginado con filtro opcional por `estado` (`PENDIENTE`, `EN_REPARACION`, etc.). Personal del taller (`ADMIN`, `RECEPCION`, `MECANICO`).
  - `GET /ordenes/{id}`: Detalle completo de orden. Personal del taller o cliente dueño del vehículo (403 si pertenece a otro cliente) (RN-17). Precarga estricta (`selectinload`) de vehículo, cliente asociado, ítems con repuestos e historial con estados.
  - `GET /mis-ordenes`: Autoservicio para rol `CLIENTE` autenticado, filtrando estrictamente por las órdenes de los vehículos pertenecientes al cliente en sesión (RN-17).

- **Máquina de transiciones y terminación con descuento atómico de stock**:
  - `POST /ordenes/{id}/iniciar`: Rol `MECANICO`. Transición `PENDIENTE` → `EN_REPARACION`. Asigna `mecanico_id = current_user.id` e inserta fila en `historial_estado_orden` (RN-11). Rechaza con 409 si el estado actual no es `PENDIENTE`.
  - `POST /ordenes/{id}/terminar`: Mecánico asignado a la orden o rol `ADMIN` (403 si otro mecánico intenta terminarla). Transición `EN_REPARACION` → `TERMINADA`. En una única transacción de `UnitOfWork`:
    - Verifica stock suficiente para cada ítem (`repuesto.stock >= item.cantidad`). Si algún repuesto no alcanza, lanza excepción de dominio, el UoW ejecuta rollback total (no se modifica stock ni estado) y responde HTTP 409 (RN-13).
    - Si el stock es suficiente, descuenta el stock de cada repuesto (RN-14), crea los registros correspondientes en `movimiento_stock` con cantidad negativa y motivo referenciando la orden, actualiza el estado a `TERMINADA` e inserta el historial de estado.
    - Tras confirmar (`commit`) la transacción, encola el aviso al cliente mediante `BackgroundTasks` (`asyncio.sleep(0.5)` con mensaje de log) (sección 3.9).

- **Cancelación de órdenes y precedencia de permisos (RN-12)**:
  - `POST /ordenes/{id}/cancelar`: Roles `RECEPCION`, `ADMIN` o cliente dueño del vehículo.
  - Precedencia estricta de validación: primero se verifica la autorización del usuario sobre la orden (403 si no le pertenece), y recién después se evalúa si el estado permite la cancelación (409 si la orden no está en estado `PENDIENTE`).

## Capabilities

### New Capabilities
- `ordenes-and-background-tasks`: Gestión integral del ciclo de vida de órdenes de trabajo (apertura, asignación, terminación atómica con control de inventario, cancelación con precedencia de permisos y aviso en segundo plano con BackgroundTasks).

### Modified Capabilities
<!-- No se modifican los contratos normativos de capabilities previas -->

## Impact

- **Módulos afectados**:
  - `app/modules/ordenes/schemas.py`: Creación de DTOs de entrada y salida con validación estricta (`extra="forbid"`).
  - `app/modules/ordenes/repository.py`: Repositorios para `EstadoOrden`, `OrdenTrabajo`, `ItemOrden` e `HistorialEstadoOrden`.
  - `app/modules/ordenes/unit_of_work.py`: `OrdenesUnitOfWork` componiendo repositorios de órdenes, repuestos y movimientos de stock.
  - `app/modules/ordenes/service.py`: Reglas de negocio RN-10 a RN-13, RN-17 y RN-19.
  - `app/modules/ordenes/router.py`: Montaje de endpoints abiertos y protegidos según matriz RBAC.
  - `main.py`: Inclusión del router de órdenes en los grupos correspondientes.
- **Riesgos y dependencias**:
  - La transacción de `terminar` orden debe asegurar que ninguna fila en `movimiento_stock` ni `orden_trabajo` persista si falla la comprobación de stock (RN-13).
  - El trigger de sólo agregado instalado en la migración 002 protege `historial_estado_orden` y `movimiento_stock`: las inserciones deben ser nuevas filas sin mutaciones.
