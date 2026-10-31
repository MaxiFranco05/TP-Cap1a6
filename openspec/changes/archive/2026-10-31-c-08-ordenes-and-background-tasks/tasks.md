# Tasks: Órdenes de Trabajo y Background Tasks (C-08)

## 1. DTO Schemas, Repositorios y Unit of Work

- [x] 1.1 Implementar esquemas DTO en `app/modules/ordenes/schemas.py` con validación estricta (`extra="forbid"`), sin precios ni totales en inputs (`ItemOrdenInput`, `CrearOrdenRequest`, `OrdenTrabajoDetalleResponse`, `OrdenTrabajoResumenResponse`, `EstadoOrdenResponse`, `HistorialEstadoOrdenResponse`) y verificar con tests unitarios de validación.
- [x] 1.2 Implementar `EstadoOrdenRepository` (heredando de `ReadOnlyRepository[EstadoOrden]`), `ItemOrdenRepository` e `HistorialEstadoOrdenRepository` en `app/modules/ordenes/repository.py` y verificar métodos de lectura y restricciones con tests.
- [x] 1.3 Implementar `OrdenTrabajoRepository` con métodos de consulta y precarga anticipada (`selectinload` de vehículo, cliente, items con repuesto e historial) para prevenir el problema N+1 y verificar con test de conteo de consultas.
- [x] 1.4 Implementar `OrdenesUnitOfWork` en `app/modules/ordenes/unit_of_work.py` componiendo repositorios de órdenes, items, estados, historial, repuestos, movimientos de stock y vehículos, verificando commit y rollback atómico con tests.

## 2. Lógica de Dominio y Servicios (Strict TDD)

- [x] 2.1 Implementar en `OrdenesService` la consulta de catálogo `listar_estados()` y la creación atómica `crear_orden()` (validación de catálogo no vacío RN-19, copiado de precios de repuestos, cálculo de total por servidor y primer registro de historial RN-10); verificar con tests RED/GREEN/TRIANGULATE.
- [x] 2.2 Implementar en `OrdenesService` la transición `iniciar_orden()` (rol mecánico, autoasignación de `mecanico_id`, cambio a `EN_REPARACION` y registro de historial RN-11); verificar rechazos (403 si no es mecánico, 409 si no está pendiente) con tests.
- [x] 2.3 Implementar en `OrdenesService` la finalización transaccional `terminar_orden()` (validación de mecánico asignado o admin, comprobación y descuento atómico de stock, inserción en `movimiento_stock`, rollback total ante falta de stock RN-13 y RN-14); verificar con tests unitarios y de integración.
- [x] 2.4 Implementar en `OrdenesService` la cancelación `cancelar_orden()` con precedencia estricta de comprobación (403 ante usuario ajeno antes de 409 por estado no cancelable RN-12); verificar con tests.
- [x] 2.5 Implementar en `OrdenesService` las lecturas con aislamiento de clientes `obtener_orden_detalle()` y `listar_mis_ordenes()` (restringiendo a vehículos del cliente autenticado RN-17); verificar con tests de autorización.

## 3. Endpoints HTTP, Background Tasks e Integración

- [x] 3.1 Implementar corutina asincrónica de notificación `notificar_cliente_orden_terminada` simulada con `await asyncio.sleep(0.5)` y logging estructurado para ejecución tras commit con `BackgroundTasks`.
- [x] 3.2 Construir endpoints HTTP en `app/modules/ordenes/router.py` (`GET /estados-orden`, `POST /ordenes`, `GET /ordenes`, `GET /ordenes/{id}`, `POST /ordenes/{id}/iniciar`, `POST /ordenes/{id}/terminar`, `POST /ordenes/{id}/cancelar`, `GET /mis-ordenes`) y registrarlos en `main.py` dentro de los grupos de rutas correspondientes.
- [x] 3.3 Ejecutar la suite completa de pruebas en `tests/test_ordenes_background_tasks.py` cubriendo casos de éxito, errores 401, 403, 404, 409, 422 y verificación de no-bloqueo asincrónico.
