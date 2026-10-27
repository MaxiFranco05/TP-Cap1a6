# Proposal: C-06 Clientes and Vehiculos (`clientes-and-vehiculos`)

## Why

El taller mecánico necesita gestionar fichas de clientes (tanto clientes presenciales sin cuenta web como clientes auto-registrados) y la flota de vehículos asociados a cada uno para poder abrirles órdenes de trabajo, consultar su estado y habilitar el autoservicio del cliente (`/mis-vehiculos`). Asimismo, el ciclo de vida de un vehículo exige baja lógica (`borrado_en`) que impida dar de baja unidades con órdenes de trabajo abiertas (`RN-16`) pero permita volver a patentar en otro cliente un vehículo previamente vendido y dado de baja (`RN-01`).

## What Changes

- **Esquemas Pydantic v2 estrictos (`app/modules/clientes/schemas.py`)**:
  - Esquemas de entrada `CrearClienteRequest` (`nombre`, `documento`, `telefono`) y `CrearVehiculoRequest` (`patente`, `marca`, `modelo`, `anio` validado entre `1950` y `2100`) con `ConfigDict(extra="forbid")`.
  - Esquemas de salida `VehiculoResponse` y `ClienteResponse` (incluyendo los vehículos activos precargados mediante `selectinload`) con `ConfigDict(from_attributes=True)`.
- **Repositorios y Unit of Work (`app/modules/clientes/repository.py`, `app/core/unit_of_work.py`)**:
  - `ClienteRepository(BaseRepository[Cliente])`: consultas por documento, por `usuario_id`, y `get_by_id_with_vehiculos(id)` utilizando `selectinload` sobre la relación `Cliente.vehiculos` filtrando activos (`borrado_en IS NULL`) para evitar lazy loading y problemas N+1.
  - `VehiculoRepository(SoftDeleteRepository[Vehiculo])`: búsqueda por patente activa, listado de vehículos activos por `cliente_id`, y verificación de órdenes abiertas (`has_open_orders`) consultando `OrdenTrabajo` unida a `EstadoOrden` donde `es_final == False`.
  - Integración de `clientes` y `vehiculos` en el `UnitOfWork`.
- **Capa de Servicio (`app/modules/clientes/service.py`)**:
  - Alta de clientes sin usuario (`usuario_id = None`) validando unicidad de `documento` (`409 Conflict`, `RN-01`).
  - Consulta de cliente por ID con sus vehículos activos (`404 Not Found` si no existe).
  - Alta de vehículo asociado a un cliente existente (`404 Not Found` si el cliente no existe; `409 Conflict` si la patente ya está activa en cualquier vehículo vigente; permite reutilizar patentes con `borrado_en IS NOT NULL` según `RN-01`).
  - Baja lógica de vehículo (`DELETE /vehiculos/{id}` → `204 No Content`): verifica que el vehículo exista y esté activo (`404 Not Found`) y que no posea órdenes de trabajo abiertas con `es_final = False` (`409 Conflict`, `RN-16`).
  - Consulta de autoservicio (`GET /mis-vehiculos`): devuelve exclusivamente los vehículos activos pertenecientes al `Cliente` vinculado al usuario autenticado (`RN-17`).
- **Router y Dependencias (`app/modules/clientes/router.py`, `app/core/dependencies.py`, `main.py`)**:
  - Exposición en el grupo protegido de `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}` (restringidos a roles `RECEPCION` y `ADMIN`) y `GET /mis-vehiculos` (usuario autenticado con ficha de cliente).
  - Contrato de dependencias de autenticación/autorización (`get_current_user`, `requiere_rol`) en `app/core/dependencies.py` compatible con la integración paralela de `C-04` y `C-05`.

## Capabilities

### New Capabilities
- `clientes-vehiculos`: Gestión de fichas de clientes, alta y baja lógica de vehículos con validación de órdenes abiertas (`RN-16`), reutilización de patentes dadas de baja (`RN-01`), carga anticipada con `selectinload` y autoservicio aislado de vehículos propios (`RN-17`).

### Modified Capabilities
<!-- Ninguna capacidad existente cambia sus requisitos a nivel de especificación. -->

## Impact

- **Nuevos archivos**:
  - `app/modules/clientes/schemas.py`
  - `app/modules/clientes/repository.py`
  - `app/modules/clientes/service.py`
  - `app/modules/clientes/router.py`
  - `app/core/dependencies.py` (contratos base de inyección para usuario autenticado y verificación de roles/UoW en caso de ejecutarse antes del merge de `C-04`/`C-05`)
  - `tests/test_clientes_vehiculos.py`
- **Archivos modificados**:
  - `app/core/unit_of_work.py` (exposición de repositorios `clientes` y `vehiculos` en la sesión compartida)
  - `main.py` (registro del router de clientes y vehículos)
