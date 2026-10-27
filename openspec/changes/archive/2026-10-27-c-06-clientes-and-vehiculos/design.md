# Design: C-06 Clientes and Vehiculos (`clientes-and-vehiculos`)

## Context

Los modelos `Cliente`, `Vehiculo`, `OrdenTrabajo` y `EstadoOrden` ya se encuentran implementados y migrados en `C-02` (`app/modules/clientes/models.py` y `app/modules/ordenes/models.py`), y las clases base `BaseRepository[T]`, `SoftDeleteRepository[T]` y `UnitOfWork` ya están operativas desde `C-03` (`app/core/repository.py`, `app/core/unit_of_work.py`). Ver `proposal.md` para la motivación funcional.

Dado que `C-04` y `C-05` están siendo desarrollados en paralelo en el equipo, este diseño contempla contratos de dependencias en `app/core/dependencies.py` (`get_uow`, `get_current_user`, `requiere_rol`) desacoplados y fácilmente reemplazables o integrables sin fricción al unificar ramas.

## Goals / Non-Goals

**Goals:**
- Implementar repositorios concretos `ClienteRepository` y `VehiculoRepository` reutilizando `BaseRepository` y `SoftDeleteRepository`.
- Garantizar carga anticipada (`selectinload`) de vehículos activos al consultar `GET /clientes/{id}` (Regla Dura #4, cero lazy loading).
- Asegurar el cumplimiento estricto de `RN-01` (unicidad de documento y patente activa con reutilización tras baja lógica), `RN-16` (bloqueo de baja lógica de vehículo con órdenes abiertas donde `es_final = False`) y `RN-17` (aislamiento de `/mis-vehiculos` por usuario autenticado).
- Mantener esquemas Pydantic v2 estrictos con `extra="forbid"` en todas las entradas y `from_attributes=True` en las salidas.

**Non-Goals:**
- No implementa el flujo de auto-registro web `POST /auth/registro` (alcance de `C-04`).
- No implementa apertura o transición de órdenes de trabajo (alcance de `C-08`).

## Decisions

### 1. Carga anticipada filtrada de vehículos activos en `ClienteRepository`
- **Decisión**: Implementar `get_by_id_with_vehiculos(cliente_id: int)` en `ClienteRepository` utilizando `select(Cliente).where(Cliente.id == cliente_id).options(selectinload(Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None))))` junto con `execution_options(populate_existing=True)`.
- **Justificación**: Cumple la Regla Dura #4 (`selectinload` obligatorio, cero lazy loading en `AsyncSession`) y asegura que `GET /clientes/{id}` devuelva en exactamente 2 queries constantes la ficha del cliente y únicamente sus vehículos activos (`RN-16`), sin filtrar unidades dadas de baja en memoria ni disparar `MissingGreenlet`.
- **Alternativas descartadas**: Cargar todos los vehículos y filtrarlos en Python dentro del servicio (ensucia la colección del modelo en sesión o exige reconstruir el DTO manualmente).

### 2. Verificación de órdenes abiertas en `VehiculoRepository.has_open_orders` (`RN-16`)
- **Decisión**: Ejecutar una consulta `SELECT EXISTS` (o `SELECT 1 ... LIMIT 1`) uniendo `OrdenTrabajo` con `EstadoOrden` (`JOIN estado_orden ON orden_trabajo.estado_id = estado_orden.id`) filtrando por `OrdenTrabajo.vehiculo_id == vehiculo_id` y `EstadoOrden.es_final.is_(False)`.
- **Justificación**: La regla `RN-16` define una orden abierta como aquella cuyo estado en el catálogo `estado_orden` tiene `es_final = False`. Consultar directamente contra el booleano del catálogo evita acoplar el repositorio de vehículos a códigos de texto fijos y aprovecha el índice en `orden_trabajo.vehiculo_id`.

### 3. Contrato de dependencias (`app/core/dependencies.py`) para desarrollo paralelo con `C-04`/`C-05`
- **Decisión**: Proveer en `app/core/dependencies.py` el proveedor `get_uow(request: Request)` (que instancia `UnitOfWork(request.app.state.session_factory)`) y las dependencias `get_current_user` / `requiere_rol(*roles: str)`. Si `C-04`/`C-05` aún no están fusionados en la rama, `get_current_user` verificará la cookie `access_token` o devolverá `401 Unauthorized`, permitiendo tanto el uso real como `app.dependency_overrides` en los tests de integración HTTP de `C-06`.
- **Justificación**: Permite desarrollar y probar `C-06` de extremo a extremo al 100% sin bloquearse por `C-04`/`C-05`, respetando las firmas estándar del proyecto.

## Risks / Trade-offs

- **[Risk] Colisión de nombres al integrar `app/core/dependencies.py` y `app/core/unit_of_work.py` con `C-04`/`C-05`** → **Mitigation**: Mantener firmas canónicas (`get_uow`, `get_current_user`, `requiere_rol`) y registrar `clientes: ClienteRepository` y `vehiculos: VehiculoRepository` como atributos del `UnitOfWork` en `__aenter__`, siguiendo exactamente `knowledge-base/08_arquitectura_propuesta.md`.
- **[Risk] Violación concurrente de unicidad de `documento` o `patente` activa** → **Mitigation**: Además de la verificación previa en el servicio para dar mensajes descriptivos (`409 Conflict`), los índices únicos en PostgreSQL (`cliente.documento` y `uq_vehiculo_patente_activa`) y el manejador global de `IntegrityError` (`RN-18`) garantizan que ninguna condición de carrera termine en HTTP 500.
