# Design: C-07 Repuestos e Inventario (`c-07-repuestos-and-inventario`)

## Context

Los modelos SQLModel `Repuesto`, `MovimientoStock` e `HistorialPrecioRepuesto` ya fueron definidos en `app/modules/repuestos/models.py` e impactados en PostgreSQL mediante las migraciones Alembic `001_initial_schema.py` (incluyendo el índice único parcial `ix_repuesto_codigo_vigente` con `WHERE borrado_en IS NULL` y las restricciones `ck_repuesto_precio_positivo`, `ck_repuesto_stock_no_negativo`, `ck_movimiento_stock_cantidad_no_cero`, `ck_historial_precio_repuesto_nuevo_positivo` y `ck_historial_precio_repuesto_distinto`) y `002_append_only_triggers.py` (disparadores PL/pgSQL `trg_<tabla>_solo_agregado` que invocan `rechazar_mutacion_solo_agregado()`). Además, el proyecto ya cuenta con `BaseRepository` y `SoftDeleteRepository` (`app/core/repository.py`), `UnitOfWork` (`app/core/unit_of_work.py`), `PaginacionWrapper` y `crear_paginacion` (`app/core/paginacion.py`), y las dependencias de autorización RBAC y `router_protegido` (`app/core/dependencies.py`, `main.py`). Ver `proposal.md` para la motivación funcional.

## Goals / Non-Goals

**Goals:**
- Completar las capas de esquemas, repositorios, `UnitOfWork`, servicio y router HTTP del módulo `app/modules/repuestos/` cumpliendo las 10 Reglas Duras de `AGENTS.md`.
- Centralizar toda modificación de `repuesto.stock` en un único punto transaccional que actualice el stock e inserte el `MovimientoStock` correspondiente (`RN-14`), listo para ser reutilizado por `C-08` al finalizar órdenes.
- Garantizar la atomicidad entre el cambio efectivo de `repuesto.precio` y el registro en `historial_precio_repuesto` (`RN-20`) usando `model_dump(exclude_unset=True)` (Regla Dura #2).
- Proveer búsqueda por descripción con parámetros ligados (`ILIKE`) y paginación consistente en `GET /repuestos`.
- Verificar con pruebas automatizadas los casos oficiales `C-14`, `C-15` y `C-16`.

**Non-Goals:**
- Implementar el descuento de stock por finalización de orden de trabajo (`POST /ordenes/{id}/terminar`), que corresponde a `C-08` (el cual consumirá el punto único de escritura de stock creado aquí).
- Bloqueo pesimista (`SELECT FOR UPDATE`) sobre filas de `repuesto` ante concurrencia extrema, explícitamente fuera del alcance de los Capítulos 1 a 6 según `SU-03`.

## Decisions

### 1. Punto único de escritura de stock (`RN-14`)
- **Decisión**: Implementar `RepuestosService.registrar_movimiento_stock(uow, repuesto, cantidad, motivo, usuario_id, orden_id=None)` como la **única** función autorizada para mutar `repuesto.stock`. Esta función verifica que `cantidad != 0` y que `repuesto.stock + cantidad >= 0` (lanzando HTTP `409 Conflict` si el saldo resultante fuera negativo o HTTP `422` si `cantidad == 0`), actualiza `repuesto.stock += cantidad` mediante `uow.repuestos.update(repuesto)` e inserta `MovimientoStock(repuesto_id=repuesto.id, orden_id=orden_id, usuario_id=usuario_id, cantidad=cantidad, motivo=motivo)` mediante `uow.movimientos_stock.add(...)` dentro de la misma sesión transaccional del `UnitOfWork`.
- **Alternativas consideradas**: Actualizar `repuesto.stock` directamente en cada caso de uso (`crear_repuesto`, `reponer_stock`, `terminar_orden`).
- **Justificación**: Cumple estrictamente `RN-14` y el Ejercicio 6 de la consigna oficial (*"El stock se escribe en un único punto (RN-14), que usan la reposición y la terminación de órdenes"*), haciendo imposible alterar existencias sin dejar su asiento contable en `movimiento_stock`.

### 2. Manejo de `stock_inicial == 0` frente a `ck_movimiento_stock_cantidad_no_cero`
- **Decisión**: En `POST /repuestos`, el esquema `CrearRepuestoRequest` acepta `stock_inicial: int = Field(default=0, ge=0)`. El servicio instancia `Repuesto(..., stock=0)` y ejecuta `flush()` vía `uow.repuestos.add(repuesto)`. Si `data.stock_inicial > 0`, invoca `registrar_movimiento_stock` con `cantidad=data.stock_inicial` y `motivo="Stock inicial"`. Si `data.stock_inicial == 0`, no inserta fila en `movimiento_stock`.
- **Alternativas consideradas**: Insertar un `MovimientoStock` con `cantidad=0` cuando `stock_inicial=0`.
- **Justificación**: La tabla `movimiento_stock` tiene la restricción `CheckConstraint("cantidad <> 0", name="ck_movimiento_stock_cantidad_no_cero")`; un movimiento de cantidad cero no representa variación de stock y violaría la integridad relacional.

### 3. Actualización parcial con `exclude_unset=True` y asiento condicional de precio (`RN-20`, Reglas Duras #1, #2 y #9)
- **Decisión**:
  - `ActualizarRepuestoRequest` define únicamente `descripcion: str | None = Field(default=None, min_length=1)` y `precio: Decimal | None = Field(default=None, gt=Decimal("0"), max_digits=10, decimal_places=2)` con `ConfigDict(extra="forbid", str_strip_whitespace=True)`. Enviar `"stock"` en el JSON produce automáticamente HTTP `422` (`RN-14`).
  - `RepuestosService.actualizar_repuesto` extrae `cambios = data.model_dump(exclude_unset=True)`. Si se envió `"descripcion"` o `"precio"` con valor `None` explícito en el JSON, se rechaza con HTTP `422`.
  - Si `"precio"` está en `cambios`, se cuantiza a 2 decimales (`Decimal("0.01")`) y se compara contra `precio_anterior`. Sólo si `nuevo_precio != precio_anterior` se actualiza `repuesto.precio = nuevo_precio` y se inserta `HistorialPrecioRepuesto(repuesto_id=repuesto.id, usuario_id=usuario_actual.id, precio_anterior=precio_anterior, precio_nuevo=nuevo_precio)` en el mismo `UnitOfWork` (`RN-20`).
- **Alternativas consideradas**: Insertar fila en `historial_precio_repuesto` siempre que `"precio"` venga en el payload de `PATCH`.
- **Justificación**: Cumple `RN-20` y respeta `ck_historial_precio_repuesto_distinto` (`precio_nuevo <> precio_anterior`), evitando fallos de constraint o registros espurios cuando un cliente envía el mismo precio vigente.

### 4. Búsqueda paginada con parámetros ligados y conteo unificado (`GET /repuestos`)
- **Decisión**: `RepuestoRepository` implementa un método auxiliar `_apply_search_filter(stmt, q: str | None)` que aplica `Repuesto.borrado_en.is_(None)` y, si `q` contiene texto no vacío, añade `Repuesto.descripcion.ilike(f"%{q}%")` mediante expresiones parametrizadas de SQLAlchemy. Tanto `search_active(q, offset, limit)` (ordenado por `Repuesto.id.asc()`) como `count_active(q)` reutilizan exactamente el mismo predicado, pasando el resultado a `crear_paginacion(items, total, params.page, params.size)`.
- **Alternativas consideradas**: Filtrar en memoria o construir SQL con f-strings.
- **Justificación**: Previene inyección SQL (validado con `q=' OR '1'='1` en el caso oficial C-15/C-16) y garantiza coherencia matemática entre `total`, `pages` y la página solicitada (`422` cuando `page > pages`).

### 5. Conservación y consulta de historiales en repuestos dados de baja (`RN-16`)
- **Decisión**: Mientras `GET /repuestos/{id}`, `PATCH /repuestos/{id}`, `DELETE /repuestos/{id}` y `POST /repuestos/{id}/reponer` buscan el repuesto mediante `uow.repuestos.get_by_id(id)` (que exige `borrado_en IS NULL`), los endpoints de auditoría `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios` verifican la existencia del repuesto con `uow.repuestos.get_by_id_including_deleted(id)` antes de listar sus registros ordenados por `id.asc()`.
- **Alternativas consideradas**: Usar `get_by_id(id)` también en `/movimientos` y `/precios`.
- **Justificación**: `RN-16` establece que cuando un repuesto se da de baja lógicamente deja de aparecer en el catálogo operativo, pero sus registros históricos se conservan para auditoría; sólo si el `id` jamás existió se responde HTTP `404 Not Found`.

### 6. Traducción de errores de integridad de PostgreSQL (Regla Dura #10)
- **Decisión**: Además de la verificación previa en servicio (`get_by_codigo(data.codigo)` para repuestos activos), capturar cualquier `sqlalchemy.exc.IntegrityError` al ejecutar `flush()` / `commit()` en el servicio de repuestos y traducirlo a `HTTPException(status_code=409, detail="Ya existe un repuesto activo con ese código")` o `422` según corresponda, sin exponer trazas ni nombres de tablas/índices de PostgreSQL al cliente.

## Risks / Trade-offs

- **[Risk] Envío de `null` explícito en campos opcionales de `PATCH /repuestos/{id}` (ej. `{"precio": null}` o `{"descripcion": null}`)** → **Mitigación**: Validar en `ActualizarRepuestoRequest` o en `RepuestosService.actualizar_repuesto` que si una clave está presente en `model_dump(exclude_unset=True)`, su valor no sea `None`, devolviendo HTTP `422 Unprocessable Entity` antes de tocar la base de datos.
- **[Risk] Desfase de precisión decimal al comparar `precio_anterior` y `precio_nuevo`** → **Mitigación**: Normalizar ambos valores con `.quantize(Decimal("0.01"))` antes de compararlos con `!=`.
