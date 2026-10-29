# Design: C-05 RBAC Authorization and Isolation (`c-05-rbac-authorization-and-isolation`)

## Context

En `C-04` se implementó la autenticación por cookie `HttpOnly` (`access_token`), el hashing `bcrypt` fuera del *event loop* y los endpoints `/auth/*` en el grupo abierto (`router_abierto`). Asimismo, `app/core/dependencies.py` ya cuenta con `get_current_user`, `get_current_active_user` y `requiere_rol` / `require_roles`.

En `C-05` corresponde completar la capa de gobierno de identidad y autorización: montar el control de cambio obligatorio de contraseña (`get_current_active_user`) una única vez sobre `router_protegido` en `main.py`, proveer `get_current_cliente` en `app/core/dependencies.py`, e implementar los endpoints protegidos de administración de personal y roles (`POST /usuarios`, `GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles`, `DELETE /usuarios/{id}/roles/{rol}`) y de auditoría (`GET /eventos`), verificando los casos oficiales `C-09`, `C-10` y `C-11`. Ver `proposal.md` para la motivación completa.

## Goals / Non-Goals

**Goals:**
- Garantizar en un único punto (`router_protegido` en `main.py`) que ningún usuario con `debe_cambiar_password = True` pueda consumir rutas protegidas (`RN-06`).
- Implementar el ciclo completo de asignaciones de rol en PostgreSQL (`RN-03`, `RN-04`), incluyendo el cierre automático de asignaciones vencidas al reasignar un rol y la validación estricta de `vence_en` (`422` para fechas sin zona horaria o en el pasado).
- Asegurar la autoprotección de `ADMIN` (`RN-05`) tanto frente a auto-revocación como frente a la revocación del último administrador activo vigente.
- Registrar en `evento_seguridad` las altas administrativas de personal y las asignaciones y revocaciones de roles dentro de la misma transacción `UnitOfWork`, y exponer su consulta paginada en `GET /eventos`.

**Non-Goals:**
- Modificar los endpoints de autenticación del grupo abierto (`/auth/*`) ya completados en `C-04`.
- Implementar el módulo de órdenes de trabajo (`/ordenes`, `/mis-ordenes`), que corresponde a `C-08`.

## Decisions

### 1. Montaje centralizado de `get_current_active_user` en `router_protegido` (`main.py`)
- **Decisión**: Declarar `router_protegido = APIRouter(dependencies=[Depends(get_current_active_user)])` en `main.py` e incluir allí los routers protegidos (`usuarios_router`, `eventos_router`, `clientes_router`).
- **Por qué**: Cumple de manera exacta la arquitectura en dos grupos de rutas descripta en la consigna (`TP_Cap1a6_Consigna.pdf` Ejercicio 5: *"dos grupos de rutas en `main.py` —uno abierto y uno protegido, que lleva el control montado una sola vez— porque FastAPI suma dependencias y no las resta"*). Así, cualquier endpoint montado en `router_protegido` rechaza con `403 Forbidden` si `debe_cambiar_password == True`, incluso cuando el endpoint solo requiere estar autenticado (como `GET /mis-vehiculos`).
- **Alternativas descartadas**: Repetir `Depends(get_current_active_user)` manualmente en cada endpoint individual (propenso a olvidos en futuros módulos).

### 2. Reasignación de roles vencidos vs. conflicto en roles vigentes (`RN-03`)
- **Decisión**: Como la tabla `asignacion_rol` posee el índice único parcial `ix_asignacion_rol_usuario_rol_vigente` sobre `(usuario_id, rol) WHERE revocada_en IS NULL`, una fila cuyo `vence_en` ya pasó (`vence_en <= NOW()`) pero que nunca fue revocada manualmente sigue teniendo `revocada_en IS NULL`. En `POST /usuarios/{id}/roles`:
  1. Consultar `get_open_by_usuario_and_rol(usuario_id, rol)` (`WHERE revocada_en IS NULL`).
  2. Si existe y sigue vigente (`vence_en IS NULL OR vence_en > now`), lanzar `HTTPException(409, detail="El usuario ya posee una asignación activa para ese rol.")` (`RN-03`).
  3. Si existe pero ya venció (`vence_en <= now`), cerrar esa fila asignando `existente.revocada_en = now` y ejecutando `await self.uow.asignaciones_rol.update(existente)` (`flush()`) antes de insertar la nueva fila `AsignacionRol`.
- **Por qué**: Respeta simultáneamente la restricción física del índice parcial `WHERE revocada_en IS NULL`, la regla `RN-03` y la especificación funcional (*"reasignar un rol vencido cierra la fila anterior y abre una nueva"*), preservando la trazabilidad histórica completa.
- **Alternativas descartadas**: Sobreescribir `vence_en` en la fila existente (destruiría el historial de la asignación anterior).

### 3. Validación de `vence_en` en `AsignarRolRequest` (`422` vs `409`)
- **Decisión**: Validar en `AsignarRolRequest` mediante `@field_validator("vence_en")` que, si `vence_en` no es `None`:
  - Posea zona horaria explícita (`v.tzinfo is not None and v.tzinfo.utcoffset(v) is not None`); de lo contrario lanza `ValueError` → HTTP `422`.
  - Sea estrictamente mayor que `datetime.now(timezone.utc)`; de lo contrario lanza `ValueError` → HTTP `422`.
  - Se normalice a UTC (`v.astimezone(timezone.utc)`).
- **Por qué**: La consigna establece explícitamente que una fecha sin zona horaria es ambigua y una fecha que ya pasó no colisiona con ningún estado persistido, por lo que ambas constituyen errores de validación de entrada (`422 Unprocessable Entity`) y nunca `409 Conflict`.

### 4. Autoprotección de `ADMIN` en `DELETE /usuarios/{id}/roles/{rol}` (`RN-05`)
- **Decisión**: Evaluar en `UsuariosService.revocar_rol`:
  1. Existencia del usuario `{id}` (`404` si no existe).
  2. Si `rol == RolEnum.ADMIN` y `usuario_id == admin_actual.id`: rechazar de inmediato con `409 Conflict` (ningún administrador puede quitarse su propio rol `ADMIN`).
  3. Existencia de asignación abierta (`revocada_en IS NULL`) para `(usuario_id, rol)` (`404` si no existe o ya fue revocada).
  4. Si `rol == RolEnum.ADMIN`: contar mediante `AsignacionRolRepository.count_other_active_admins(excluded_usuario_id=usuario_id, now=now)` cuántos usuarios activos (`Usuario.activo == True`, `Usuario.id != usuario_id`) tienen el rol `ADMIN` abierto y no vencido. Si el resultado es `0`, rechazar con `409 Conflict`.
- **Por qué**: Garantiza las dos invariantes de `RN-05` dentro de la misma transacción antes de asentar `revocada_en = now`.

### 5. `get_current_cliente` e integración con `GET /mis-vehiculos` (`RN-17`)
- **Decisión**: Definir `get_current_cliente(current_user: Usuario = Depends(get_current_active_user), session: AsyncSession = Depends(get_session)) -> Cliente | None` en `app/core/dependencies.py` consultando `Cliente` por `Cliente.usuario_id == current_user.id`. En `GET /mis-vehiculos`, utilizar la ficha resuelta (devolviendo `[]` si el usuario autenticado no tiene ficha de cliente asociada y la lista de vehículos activos de `cliente.id` cuando sí la tiene).
- **Por qué**: Centraliza la resolución de identidad de cliente en `app/core/dependencies.py` tal como requiere `CHANGES.md` para todas las rutas `/mis-*` (`C-06` y `C-08`), manteniendo el 100% de compatibilidad con los tests existentes de `C-04` y `C-06`.

## Risks / Trade-offs

- **[Risk] Colisión en el índice parcial `ix_asignacion_rol_usuario_rol_vigente` al reasignar un rol vencido** → **Mitigation**: Ejecutar `flush()` del cierre (`existente.revocada_en = now`) en `AsignacionRolRepository.update` antes de hacer `add()` de la nueva asignación dentro del mismo `UnitOfWork`.
- **[Risk] Separación de rutas `/auth/*` (abiertas) vs `/usuarios/*` y `/eventos` (protegidas) en `app/modules/usuarios/router.py`** → **Mitigation**: Exportar `auth_router` (montado en `router_abierto`) y `usuarios_router` / `eventos_router` (montados en `router_protegido`) desde `app/modules/usuarios/router.py`.
