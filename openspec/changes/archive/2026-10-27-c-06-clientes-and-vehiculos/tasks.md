# Tasks: C-06 Clientes and Vehiculos (`clientes-and-vehiculos`)

## 1. Esquemas Pydantic v2 Estrictos (`app/modules/clientes/schemas.py`)

- [x] 1.1 Escribir tests unitarios (RED) y luego implementar (GREEN) en `app/modules/clientes/schemas.py` los esquemas de entrada `CrearClienteRequest` (`nombre`, `documento`, `telefono`) y `CrearVehiculoRequest` (`patente`, `marca`, `modelo`, `anio` con `Field(ge=1950, le=2100)`) ambos con `ConfigDict(extra="forbid")`, y los esquemas de salida `VehiculoResponse` y `ClienteResponse` (con `vehiculos: list[VehiculoResponse] = []`) con `ConfigDict(from_attributes=True)`, verificando con `pytest tests/test_clientes_vehiculos.py` que campos extra y años fuera de `1950..2100` fallen con `ValidationError`.

## 2. Repositorios de Clientes y Vehículos y Unit of Work (`app/modules/clientes/repository.py`, `app/core/unit_of_work.py`)

- [x] 2.1 Escribir tests de integración (RED) y luego implementar (GREEN) `ClienteRepository(BaseRepository[Cliente])` en `app/modules/clientes/repository.py` con `get_by_documento(documento: str)`, `get_by_usuario_id(usuario_id: int)` y `get_by_id_with_vehiculos(cliente_id: int)` usando `selectinload(Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None)))`, verificando con `pytest tests/test_clientes_vehiculos.py` que cargue únicamente vehículos activos sin disparar lazy loading.
- [x] 2.2 Escribir tests de integración (RED) y luego implementar (GREEN) `VehiculoRepository(SoftDeleteRepository[Vehiculo])` en `app/modules/clientes/repository.py` con `get_by_patente_activa(patente: str)`, `list_by_cliente_id(cliente_id: int)` (filtrando `borrado_en IS NULL`) y `has_open_orders(vehiculo_id: int)` (uniendo `OrdenTrabajo` con `EstadoOrden` donde `EstadoOrden.es_final.is_(False)`), y exponer `self.clientes` y `self.vehiculos` en `UnitOfWork.__aenter__` (`app/core/unit_of_work.py`), verificando el pase de los tests con `pytest tests/test_clientes_vehiculos.py`.

## 3. Capa de Servicio de Clientes y Vehículos (`app/modules/clientes/service.py`)

- [x] 3.1 Escribir tests (RED) y luego implementar (GREEN) en `app/modules/clientes/service.py` las operaciones de servicio para crear cliente (`409 Conflict` si el `documento` ya existe, `RN-01`), obtener cliente con sus vehículos activos (`404 Not Found` si no existe) y registrar vehículo para un cliente (`404 Not Found` si el cliente no existe, `409 Conflict` si la patente ya está activa, y `201` si la patente pertenecía a un vehículo dado de baja lógicamente según `RN-01`), verificando con `pytest tests/test_clientes_vehiculos.py`.
- [x] 3.2 Escribir tests (RED) y luego implementar (GREEN) en `app/modules/clientes/service.py` la baja lógica de vehículo (`404 Not Found` si no existe o ya fue dado de baja, `409 Conflict` si `has_open_orders` es verdadero según `RN-16`, o baja lógica `borrado_en = NOW()` en caso contrario) y el listado de vehículos propios del usuario autenticado (`RN-17`), verificando con `pytest tests/test_clientes_vehiculos.py`.

## 4. Dependencias, Router HTTP y Registro en `main.py` (`app/core/dependencies.py`, `app/modules/clientes/router.py`, `main.py`)

- [x] 4.1 Implementar contratos de dependencias en `app/core/dependencies.py` (`get_uow`, `get_current_user`, `requiere_rol`) compatibles con `C-04`/`C-05`, y crear `app/modules/clientes/router.py` exponiendo `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}` (roles `RECEPCION`, `ADMIN`) y `GET /mis-vehiculos` (usuario autenticado), registrando el router en `main.py` y verificando mediante tests HTTP con `httpx.AsyncClient` (`pytest tests/test_clientes_vehiculos.py`) todos los códigos de estado (`201`, `200`, `204`, `404`, `409`, `422`, `401`/`403`).
- [x] 4.2 Ejecutar la suite completa de pruebas (`pytest -v`) verificando que el 100% de los tests del repositorio (`C-01`, `C-02`, `C-03` y `C-06`) pasen en verde sin regresiones.
