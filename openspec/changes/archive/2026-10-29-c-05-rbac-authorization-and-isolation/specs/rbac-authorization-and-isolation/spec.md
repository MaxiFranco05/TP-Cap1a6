# Spec Delta: RBAC Authorization and Isolation (`rbac-authorization-and-isolation`)

## Purpose

Gobierna la autorización dinámica basada en roles consultados en tiempo real en PostgreSQL (`RN-04`), el bloqueo del grupo protegido ante cambio obligatorio de contraseña (`RN-06`), el aislamiento de recursos propios de clientes (`RN-17`), la administración de personal (`POST /usuarios`), la asignación y revocación histórica de roles con vigencia (`RN-03`) y autoprotección de `ADMIN` (`RN-05`), y la auditoría paginada de eventos de seguridad (`GET /eventos`).

## ADDED Requirements

### Requirement: Bloqueo de grupo protegido por contraseña provisoria y consulta de roles en tiempo real
El sistema MUST bloquear con HTTP `403 Forbidden` el acceso a cualquier ruta del grupo protegido cuando el usuario autenticado tenga `debe_cambiar_password = True` (`RN-06`), y MUST verificar los roles requeridos consultando en tiempo real la tabla `asignacion_rol` (`revocada_en IS NULL` y `vence_en IS NULL OR vence_en > NOW()`) en cada petición (`RN-04`).

#### Scenario: Bloqueo de usuario con contraseña provisoria en rutas protegidas
- **WHEN** un usuario autenticado con `debe_cambiar_password = True` invoca cualquier endpoint del grupo protegido (como `/usuarios`, `/eventos`, `/clientes` o `/mis-vehiculos`)
- **THEN** el sistema rechaza la petición con HTTP `403 Forbidden` antes de ejecutar el handler (`RN-06`)

#### Scenario: Denegación inmediata tras revocación o vencimiento de rol con la misma cookie
- **WHEN** un usuario inició sesión cuando tenía un rol activo, pero dicho rol fue revocado (`revocada_en IS NOT NULL`) o expiró (`vence_en <= NOW()`), e invoca un endpoint protegido para ese rol reutilizando la misma cookie `access_token`
- **THEN** el sistema consulta `asignacion_rol` en tiempo real y rechaza la petición con HTTP `403 Forbidden`, mientras que `GET /auth/yo` refleja la diferencia entre `roles` (en base de datos) y `roles_token` (en el JWT) (`RN-04`)

### Requirement: Alta administrativa de personal con clave provisoria (`POST /usuarios`)
El sistema MUST permitir exclusivamente a usuarios con rol `ADMIN` vigente dar de alta nuevo personal mediante `POST /usuarios`, validando `email`, `nombre` y `password` (1 a 72 bytes UTF-8, `extra="forbid"`), hasheando la contraseña fuera de la transacción, creando el usuario con `debe_cambiar_password = True` y registrando el alta en `evento_seguridad`.

#### Scenario: Alta exitosa de usuario por administrador
- **WHEN** un usuario con rol `ADMIN` vigente envía `POST /usuarios` con `email` libre, `nombre` y `password` válida (<= 72 bytes UTF-8)
- **THEN** el sistema hashea la clave fuera de la transacción, persiste el usuario con `activo = True` y `debe_cambiar_password = True`, registra un `EventoSeguridad` con el email del administrador como `actor` y responde HTTP `201 Created` sin exponer `password_hash`

#### Scenario: Rechazo por email duplicado en alta de personal
- **WHEN** un `ADMIN` envía `POST /usuarios` con un `email` que ya pertenece a otro usuario registrado
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` (`RN-01`)

#### Scenario: Rechazo por campos extra, contraseña mayor a 72 bytes UTF-8 o falta de rol ADMIN
- **WHEN** se envía `POST /usuarios` con atributos no declarados, con una contraseña mayor a 72 bytes UTF-8, o desde un usuario sin rol `ADMIN` vigente
- **THEN** el sistema responde HTTP `422 Unprocessable Entity` ante errores de esquema o HTTP `403 Forbidden` si el usuario no posee rol `ADMIN`

### Requirement: Consulta y asignación dinámica de roles con vigencia (`GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles`)
El sistema MUST permitir a un `ADMIN` consultar todas las asignaciones de rol de un usuario en `GET /usuarios/{id}/roles` y asignar roles (`ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`) en `POST /usuarios/{id}/roles` con `vence_en` opcional en UTC futuro, impidiendo duplicar asignaciones abiertas vigentes (`RN-03`) y cerrando automáticamente asignaciones vencidas previas al reasignar.

#### Scenario: Consulta de historial de roles de un usuario
- **WHEN** un `ADMIN` solicita `GET /usuarios/{id}/roles` para un usuario existente (o inexistente)
- **THEN** el sistema responde HTTP `200 OK` con la lista completa de asignaciones (vigentes, vencidas y revocadas) si el usuario existe, o HTTP `404 Not Found` si no existe

#### Scenario: Asignación exitosa de rol con o sin fecha de vencimiento
- **WHEN** un `ADMIN` envía `POST /usuarios/{id}/roles` para un usuario existente con un `rol` válido que el usuario no posee vigente y `vence_en` nulo o con fecha futura con zona horaria
- **THEN** el sistema inserta la fila en `asignacion_rol` con `otorgada_por = admin.id`, registra un `EventoSeguridad` y responde HTTP `201 Created`

#### Scenario: Conflicto al asignar un rol que ya se encuentra abierto y vigente
- **WHEN** un `ADMIN` envía `POST /usuarios/{id}/roles` con un `rol` para el cual el usuario ya tiene una asignación abierta (`revocada_en IS NULL`) y vigente (`vence_en IS NULL` o `vence_en > NOW()`)
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` (`RN-03`)

#### Scenario: Reasignación de un rol previamente vencido cerrando la fila anterior
- **WHEN** un usuario posee una asignación con `revocada_en IS NULL` pero cuyo `vence_en` ya expiró (`vence_en <= NOW()`), y un `ADMIN` envía `POST /usuarios/{id}/roles` para el mismo `rol`
- **THEN** el sistema cierra la fila vencida asignándole `revocada_en = NOW()`, inserta una nueva fila activa en la misma transacción, registra el `EventoSeguridad` y responde HTTP `201 Created`

#### Scenario: Rechazo de fecha de vencimiento sin zona horaria o en el pasado
- **WHEN** un `ADMIN` envía `POST /usuarios/{id}/roles` con un valor `vence_en` sin zona horaria (*naive*) o con una marca temporal menor o igual al instante actual
- **THEN** el sistema rechaza la petición con HTTP `422 Unprocessable Entity`

### Requirement: Revocación lógica de roles y autoprotección de administradores (`DELETE /usuarios/{id}/roles/{rol}`)
El sistema MUST permitir a un `ADMIN` revocar lógicamente un rol mediante `DELETE /usuarios/{id}/roles/{rol}` asentando `revocada_en = NOW()` sin eliminar la fila y registrando `EventoSeguridad` (`200 OK`), pero MUST rechazar con HTTP `409 Conflict` la auto-revocación del rol `ADMIN` propio o cualquier revocación que deje al sistema sin administradores activos vigentes (`RN-05`).

#### Scenario: Revocación lógica exitosa conservando la fila histórica
- **WHEN** un `ADMIN` invoca `DELETE /usuarios/{id}/roles/{rol}` sobre una asignación abierta de otro usuario (sin violar `RN-05`)
- **THEN** el sistema establece `revocada_en = NOW()`, registra un `EventoSeguridad` y responde HTTP `200 OK` con la asignación revocada, la cual permanece visible en `GET /usuarios/{id}/roles`

#### Scenario: Bloqueo de auto-revocación del propio rol ADMIN
- **WHEN** un administrador autenticado invoca `DELETE /usuarios/{su_propio_id}/roles/ADMIN` (incluso si existen otros administradores activos en el sistema)
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` y conserva el rol intacto (`RN-05`)

#### Scenario: Bloqueo de revocación cuando quedaría cero administradores vigentes
- **WHEN** se intenta revocar el rol `ADMIN` de un usuario y no existe ningún otro usuario activo con asignación `ADMIN` vigente (`revocada_en IS NULL` y `vence_en IS NULL OR vence_en > NOW()`)
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` (`RN-05`)

#### Scenario: Revocación sobre usuario o asignación abierta inexistente
- **WHEN** un `ADMIN` invoca `DELETE /usuarios/{id}/roles/{rol}` para un usuario inexistente o para un rol que el usuario no tiene abierto (`revocada_en IS NULL`)
- **THEN** el sistema responde HTTP `404 Not Found`

### Requirement: Consulta paginada de eventos de seguridad (`GET /eventos`)
El sistema MUST exponer `GET /eventos` exclusivamente para el rol `ADMIN`, devolviendo los registros de `evento_seguridad` bajo el contrato estándar `PaginacionWrapper[EventoSeguridadResponse]` (`items`, `total`, `page`, `size`, `pages`) y rechazando parámetros o páginas fuera de rango con HTTP `422 Unprocessable Entity`.

#### Scenario: Consulta paginada exitosa de eventos de seguridad por ADMIN
- **WHEN** un usuario con rol `ADMIN` solicita `GET /eventos?page=1&size=20`
- **THEN** el sistema responde HTTP `200 OK` con `PaginacionWrapper[EventoSeguridadResponse]` incluyendo los eventos registrados y los metadatos de paginación

#### Scenario: Rechazo de paginación inválida o página fuera de rango en eventos
- **WHEN** un `ADMIN` solicita `GET /eventos` con `page < 1`, `size < 1`, `size > 100` o un número de `page` mayor que `pages`
- **THEN** el sistema responde HTTP `422 Unprocessable Entity`

### Requirement: Resolución de identidad de cliente y aislamiento de recursos propios (`RN-17`)
El sistema MUST proveer la dependencia `get_current_cliente` en `app/core/dependencies.py` para resolver la entidad `Cliente` asociada al `usuario_id` autenticado en sesión y garantizar el aislamiento de datos propios en endpoints `/mis-*` (`RN-17`).

#### Scenario: Aislamiento estricto entre clientes en consulta de recursos propios
- **WHEN** un cliente autenticado consulta `GET /mis-vehiculos`
- **THEN** el sistema resuelve su ficha `Cliente` a partir del usuario en sesión y devuelve exclusivamente sus propios vehículos activos (`200 OK`), sin exponer vehículos de otros clientes (`RN-17`)
