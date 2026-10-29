# Proposal: C-05 RBAC Authorization and Isolation (`c-05-rbac-authorization-and-isolation`)

## Why

El sistema necesita administrar el ciclo de vida del personal operativo y administrativo y gobernar sus permisos mediante un control de acceso basado en roles (RBAC) consultado en tiempo real en PostgreSQL en cada petición (`RN-04`), garantizando que las revocaciones y los vencimientos surtan efecto inmediato sin esperar a que expire la cookie JWT. Asimismo, debe impedir que el taller quede acéfalo protegiendo el rol `ADMIN` contra auto-revocación o eliminación del último administrador vigente (`RN-05`), asegurar el bloqueo del grupo protegido cuando `debe_cambiar_password = True` (`RN-06`), aislar estrictamente los recursos de clientes (`RN-17`) y exponer la auditoría paginada de eventos de seguridad.

## What Changes

- **Dependencias de autorización y grupo protegido (`app/core/dependencies.py`, `main.py`)**:
  - Montaje de `Depends(get_current_active_user)` a nivel de `router_protegido` en `main.py` para garantizar en un único punto que ningún usuario con `debe_cambiar_password = True` acceda a rutas protegidas (`403 Forbidden`, `RN-06`).
  - Incorporación de `get_current_cliente` (y alias `get_usuario_actual`) en `app/core/dependencies.py` para resolver la ficha `Cliente` vinculada al usuario autenticado y asegurar el aislamiento en rutas `/mis-*` (`RN-17`).
- **Esquemas Pydantic de administración de personal, roles y auditoría (`app/modules/usuarios/schemas.py`)**:
  - `CrearUsuarioRequest` (`email`, `nombre`, `password` de 1 a 72 bytes UTF-8) con `ConfigDict(extra="forbid")`.
  - `AsignarRolRequest` (`rol: RolEnum`, `vence_en: datetime | None = None`) con `ConfigDict(extra="forbid")` y validación de que `vence_en`, cuando se envía, posea zona horaria explícita y sea una fecha futura respecto a UTC (rechazando fechas *naive* o pasadas con HTTP `422`).
  - `AsignacionRolResponse` (`id`, `usuario_id`, `rol`, `desde`, `vence_en`, `revocada_en`, `otorgada_por`) y `EventoSeguridadResponse` (`id`, `cuando`, `actor`, `accion`) con `ConfigDict(from_attributes=True)`.
- **Repositorios de asignaciones de rol y eventos (`app/modules/usuarios/repository.py`)**:
  - Ampliación de `AsignacionRolRepository` con búsqueda de todas las asignaciones de un usuario (`list_by_usuario_id`), búsqueda de asignación abierta por usuario y rol (`get_open_by_usuario_and_rol`) y conteo de otros administradores activos vigentes (`count_other_active_admins`).
  - Ampliación de `EventoSeguridadRepository` con listado paginado ordenado (`list_paginated`).
- **Servicios y Endpoints protegidos (`app/modules/usuarios/service.py`, `app/modules/usuarios/router.py`, `main.py`)**:
  - `POST /usuarios` (`ADMIN`, `201 Created`): alta de personal con contraseña provisoria (`debe_cambiar_password = True`), hashing `bcrypt` fuera de la transacción, validación de email único (`409 Conflict`) y registro en `evento_seguridad`.
  - `GET /usuarios/{id}/roles` (`ADMIN`, `200 OK`): listado completo de asignaciones de rol (vigentes, vencidas y revocadas) de un usuario (`404` si el usuario no existe).
  - `POST /usuarios/{id}/roles` (`ADMIN`, `201 Created`): asignación de rol (`ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`) con `vence_en` opcional. Si existe una asignación abierta y vigente para ese rol, responde `409 Conflict` (`RN-03`); si existe una asignación abierta pero ya vencida, cierra la fila vencida (`revocada_en = NOW()`) y abre la nueva en la misma transacción, registrando `EventoSeguridad`.
  - `DELETE /usuarios/{id}/roles/{rol}` (`ADMIN`, `200 OK`): revocación lógica (`revocada_en = NOW()`) conservando la fila histórica y registrando `EventoSeguridad`. Aplica autoprotección `RN-05`: rechaza con `409 Conflict` si un `ADMIN` intenta revocarse su propio rol `ADMIN` o si la revocación dejaría al sistema sin administradores activos vigentes; responde `404` si el usuario o la asignación abierta no existen.
  - `GET /eventos` (`ADMIN`, `200 OK`): consulta paginada de `evento_seguridad` utilizando `PaginacionWrapper[EventoSeguridadResponse]` y `crear_paginacion`.
  - Montaje de `usuarios_router` y `eventos_router` en `router_protegido` de `main.py`.

## Capabilities

### New Capabilities
- `rbac-authorization-and-isolation`: Autorización RBAC dinámica en tiempo real sobre PostgreSQL (`RN-04`), bloqueo del grupo protegido por cambio obligatorio de contraseña (`RN-06`), aislamiento de recursos de clientes (`RN-17`), alta administrativa de personal con clave provisoria (`POST /usuarios`), asignación y revocación histórica de roles con vigencia (`RN-03`) y autoprotección de `ADMIN` (`RN-05`), y consulta paginada de auditoría (`GET /eventos`).

### Modified Capabilities
<!-- No existing capability requirements are modified. -->

## Impact

- **Nuevos archivos**:
  - `tests/test_rbac_isolation.py`
- **Archivos modificados**:
  - `app/core/dependencies.py`
  - `app/modules/usuarios/schemas.py`
  - `app/modules/usuarios/repository.py`
  - `app/modules/usuarios/service.py`
  - `app/modules/usuarios/router.py`
  - `main.py`
