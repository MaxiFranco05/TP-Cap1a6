# Proposal: C-07 Repuestos e Inventario (`c-07-repuestos-and-inventario`)

## Why

El taller mecánico necesita administrar su catálogo de repuestos y el inventario físico con garantías transaccionales ACID y trazabilidad forense completa. Este cambio implementa las reglas críticas del dominio de inventario: unicidad parcial de códigos entre repuestos vigentes permitiendo reutilizar códigos dados de baja (`RN-01`), mutación de existencias exclusivamente a través de un punto único de escritura de movimientos prohibiendo la edición directa de `stock` por `PATCH` (`RN-14`), asiento obligatorio en `historial_precio_repuesto` dentro de la misma transacción únicamente cuando el precio efectivamente cambia (`RN-20`), conservación histórica tras baja lógica (`RN-16`) y verificación de inmutabilidad de tablas de sólo agregado (`RN-15`). Asimismo, provee la primitiva transaccional de ajuste de stock que consumirá `C-08` al finalizar órdenes de trabajo.

## What Changes

- **Esquemas Pydantic v2 Estrictos (`app/modules/repuestos/schemas.py`)**:
  - Creación de esquemas de entrada con `ConfigDict(extra="forbid", str_strip_whitespace=True)` (Regla Dura #1) e importes monetarios en `Decimal` (Regla Dura #9):
    - `CrearRepuestoRequest`: `codigo` (`min_length=1`), `descripcion` (`min_length=1`), `precio` (`Decimal > 0`), `stock_inicial` (`int >= 0`, default `0`).
    - `ActualizarRepuestoRequest`: `descripcion: str | None = None`, `precio: Decimal | None = None` (`> 0`). Omite deliberadamente el campo `stock` para que cualquier intento de enviarlo en `PATCH /repuestos/{id}` sea rechazado automáticamente con HTTP `422 Unprocessable Entity` (`RN-14`).
    - `ReponerStockRequest`: `cantidad` (`int > 0`), `motivo` (`str`, `min_length=1`).
  - Creación de esquemas de salida con `ConfigDict(from_attributes=True)`: `RepuestoResponse`, `MovimientoStockResponse` e `HistorialPrecioResponse`.
- **Repositorios y Unit of Work (`app/modules/repuestos/repository.py`, `app/modules/repuestos/unit_of_work.py`, `app/core/unit_of_work.py`)**:
  - `RepuestoRepository(SoftDeleteRepository[Repuesto])`: búsqueda de activos por código (`get_by_codigo`), consulta paginada y filtrada de activos por descripción (`search_active(q, offset, limit)` y `count_active(q)`) utilizando parámetros ligados (`ILIKE`) para prevenir inyección SQL, y consulta incluyendo borrados lógicos (`get_by_id_including_deleted`) para auditoría histórica (`RN-16`).
  - `MovimientoStockRepository(BaseRepository[MovimientoStock])`: inserción con `flush()` y listado histórico por `repuesto_id` ordenado cronológicamente/por ID ascendente.
  - `HistorialPrecioRepuestoRepository(BaseRepository[HistorialPrecioRepuesto])`: inserción con `flush()` y listado histórico por `repuesto_id` ordenado por ID ascendente.
  - Exposición de `repuestos`, `movimientos_stock` e `historial_precios` en `UnitOfWork` (`app/core/unit_of_work.py`) y `RepuestosUnitOfWork` (`app/modules/repuestos/unit_of_work.py`) manteniendo `commit()` y `rollback()` como potestad exclusiva del `UnitOfWork` (Regla Dura #3).
- **Servicio de Dominio y Punto Único de Escritura de Stock (`app/modules/repuestos/service.py`)**:
  - Método único de mutación de existencias (`registrar_movimiento_stock` / `ajustar_stock`) que valida `cantidad != 0` y `repuesto.stock + cantidad >= 0`, actualiza `repuesto.stock` e inserta la fila correspondiente en `movimiento_stock` dentro de la misma transacción (`RN-14`).
  - `crear_repuesto`: verifica unicidad activa de `codigo` (`409 Conflict` si existe activo; permite reutilizar `codigo` si el anterior tiene `borrado_en IS NOT NULL`, `RN-01`), crea el repuesto con `stock=0` y, si `stock_inicial > 0`, invoca el punto único de escritura de stock con `motivo="Stock inicial"` (si `stock_inicial == 0`, no inserta movimiento respetando `ck_movimiento_stock_cantidad_no_cero`).
  - `actualizar_repuesto`: aplica actualizaciones parciales con `data.model_dump(exclude_unset=True)` (Regla Dura #2). Si `precio` fue enviado y `nuevo_precio != precio_anterior`, actualiza `repuesto.precio` e inserta una fila en `historial_precio_repuesto` en la misma transacción (`RN-20`). Si `precio` no fue enviado o es idéntico al actual, no genera fila en el historial.
  - `reponer_stock`: invoca el punto único de escritura de stock con `cantidad > 0` y `motivo` (`RN-14`).
  - `eliminar_repuesto`: ejecuta baja lógica (`borrado_en = now` UTC) sobre repuestos activos (`204 No Content`, `404` si no existe o ya fue dado de baja, `RN-16`).
  - `listar_movimientos` y `listar_precios`: verifican la existencia del repuesto mediante `get_by_id_including_deleted` (permitiendo auditar repuestos dados de baja lógicamente según `RN-16`, o devolviendo `404` si el ID jamás existió) y retornan la traza histórica completa.
- **Router HTTP y Montaje en Grupo Protegido (`app/modules/repuestos/router.py`, `main.py`)**:
  - `GET /repuestos` (roles `ADMIN`, `RECEPCION`, `MECANICO`): listado paginado `PaginacionWrapper[RepuestoResponse]` con filtro opcional `q` sobre `descripcion`.
  - `GET /repuestos/{id}` (roles `ADMIN`, `RECEPCION`, `MECANICO`): detalle de repuesto activo (`200` / `404`).
  - `POST /repuestos` (rol `ADMIN`): alta de repuesto con stock inicial opcional (`201` / `409` / `422`).
  - `PATCH /repuestos/{id}` (rol `ADMIN`): actualización parcial y trazabilidad de precios (`200` / `404` / `422`).
  - `DELETE /repuestos/{id}` (rol `ADMIN`): baja lógica (`204` / `404`).
  - `POST /repuestos/{id}/reponer` (rol `ADMIN`): reposición manual de stock (`200` / `404` / `422`).
  - `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios` (rol `ADMIN`): consulta de historiales (`200` / `404`).
- **Suite de Pruebas Automatizadas (`tests/test_repuestos_inventario.py`)**:
  - Cobertura integral de los casos oficiales `C-14` (protección append-only en tablas históricas `RN-15`), `C-15` (alta, reposición, búsqueda segura `q`, paginación filtrada, `PATCH` parcial con `exclude_unset=True` y rechazo de `stock` con `422` por `RN-14`) y `C-16` (trazabilidad obligatoria de cambios de precio `RN-20` y control de acceso por rol).

## Capabilities

### New Capabilities
- `repuestos-and-inventario`: Gestión del catálogo de repuestos con borrado lógico y reutilización de códigos dados de baja (`RN-01`, `RN-16`), mutación de stock centralizada por movimientos (`RN-14`), historial transaccional de precios (`RN-20`), búsqueda paginada segura y verificación de disparadores de sólo agregado (`RN-15`).

### Modified Capabilities
- Ninguna.

## Impact

- **Nuevos archivos**:
  - `app/modules/repuestos/schemas.py`
  - `app/modules/repuestos/repository.py`
  - `app/modules/repuestos/unit_of_work.py`
  - `app/modules/repuestos/service.py`
  - `app/modules/repuestos/router.py`
  - `tests/test_repuestos_inventario.py`
- **Archivos modificados**:
  - `app/core/unit_of_work.py` (registro de repositorios `repuestos`, `movimientos_stock` e `historial_precios`).
  - `main.py` (inclusión del router de repuestos en `router_protegido`).
- **Dependencias habilitadas**:
  - Desbloquea `C-08` (`ordenes-and-background-tasks`), que utilizará `RepuestoRepository` y el punto único de escritura de stock dentro del `UnitOfWork` al finalizar órdenes de trabajo (`RN-13`, `RN-14`).
