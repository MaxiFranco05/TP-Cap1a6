# Spec Delta: Clientes and Vehiculos (`clientes-vehiculos`)

## Purpose

Gobierna el registro y consulta de fichas de clientes, el alta y baja lógica de su flota de vehículos con protección contra órdenes abiertas (`RN-16`) y reutilización de patentes vendidas (`RN-01`), y la consulta aislada de autoservicio para clientes autenticados (`RN-17`).

## ADDED Requirements

### Requirement: Alta de clientes con documento único
El sistema MUST permitir a usuarios con rol `RECEPCION` o `ADMIN` dar de alta fichas de cliente mediante `POST /clientes` exigiendo `nombre`, `documento` y `telefono` bajo esquemas estrictos (`extra="forbid"`), respondiendo HTTP `201 Created` o HTTP `409 Conflict` si el `documento` ya existe (`RN-01`).

#### Scenario: Creación exitosa de cliente sin usuario web
- **WHEN** un usuario con rol `RECEPCION` o `ADMIN` envía `POST /clientes` con `nombre`, `documento` nuevo y `telefono` válido
- **THEN** el sistema persiste la ficha con `usuario_id = null` y responde HTTP `201 Created` con los datos del cliente creado

#### Scenario: Rechazo por documento duplicado
- **WHEN** se envía `POST /clientes` con un `documento` que ya pertenece a otro cliente registrado
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` sin filtrar detalles internos de la base de datos (`RN-18`)

#### Scenario: Rechazo por campos no declarados en el alta de cliente
- **WHEN** se envía `POST /clientes` incluyendo atributos adicionales no definidos en el esquema de entrada
- **THEN** el sistema rechaza la petición con HTTP `422 Unprocessable Entity`

### Requirement: Consulta de cliente con vehículos activos precargados
El sistema SHALL permitir a usuarios con rol `RECEPCION` o `ADMIN` consultar `GET /clientes/{id}` devolviendo la ficha del cliente junto con su lista de vehículos activos (`borrado_en IS NULL`) cargados anticipadamente en un número constante de consultas sin carga perezosa.

#### Scenario: Consulta exitosa de cliente con flota activa
- **WHEN** un usuario con rol `RECEPCION` o `ADMIN` solicita `GET /clientes/{id}` para un cliente existente que posee vehículos activos e inactivos
- **THEN** el sistema responde HTTP `200 OK` incluyendo la ficha del cliente y únicamente sus vehículos con `borrado_en IS NULL`

#### Scenario: Cliente inexistente en consulta por identificador
- **WHEN** se solicita `GET /clientes/{id}` con un identificador que no existe en la base de datos
- **THEN** el sistema responde HTTP `404 Not Found`

### Requirement: Registro de vehículos y reutilización de patentes dadas de baja
El sistema MUST permitir a `RECEPCION` o `ADMIN` registrar vehículos mediante `POST /clientes/{id}/vehiculos` validando `anio` entre `1950` y `2100` y unicidad de `patente` entre vehículos activos (`borrado_en IS NULL`), permitiendo reutilizar la patente de un vehículo previamente dado de baja (`RN-01`).

#### Scenario: Alta exitosa de vehículo para un cliente existente
- **WHEN** `RECEPCION` o `ADMIN` envía `POST /clientes/{id}/vehiculos` con `patente` libre, `marca`, `modelo` y `anio` entre `1950` y `2100`
- **THEN** el sistema asocia el vehículo al cliente y responde HTTP `201 Created`

#### Scenario: Conflicto por patente activa existente
- **WHEN** se intenta registrar un vehículo con una `patente` que ya está registrada y activa (`borrado_en IS NULL`)
- **THEN** el sistema rechaza el alta con HTTP `409 Conflict`

#### Scenario: Reutilización de patente tras baja lógica por venta
- **WHEN** un vehículo con patente `AA123BB` fue dado de baja lógicamente (`borrado_en IS NOT NULL`) y se envía `POST /clientes/{otro_id}/vehiculos` con la misma patente `AA123BB`
- **THEN** el sistema permite el registro en el nuevo cliente y responde HTTP `201 Created` (`RN-01`)

#### Scenario: Rechazo por año fuera de rango o cliente inexistente
- **WHEN** se envía `POST /clientes/{id}/vehiculos` con `anio` menor a `1950` o mayor a `2100`, o para un `cliente_id` inexistente
- **THEN** el sistema responde HTTP `422 Unprocessable Entity` ante año inválido o HTTP `404 Not Found` si el cliente no existe

### Requirement: Baja lógica de vehículos condicionada a órdenes abiertas
El sistema SHALL ejecutar la baja lógica en `DELETE /vehiculos/{id}` asignando la marca temporal UTC en `borrado_en` y respondiendo HTTP `204 No Content`, pero MUST bloquear la baja con HTTP `409 Conflict` si el vehículo posee al menos una orden de trabajo cuyo estado tenga `es_final = False` (`RN-16`).

#### Scenario: Baja lógica exitosa de vehículo sin órdenes abiertas
- **WHEN** `RECEPCION` o `ADMIN` invoca `DELETE /vehiculos/{id}` sobre un vehículo activo sin órdenes o únicamente con órdenes en estado final (`FINALIZADA`, `ENTREGADA`, `CANCELADA`)
- **THEN** el sistema asigna `borrado_en` con timestamp UTC y responde HTTP `204 No Content`

#### Scenario: Bloqueo de baja por orden de trabajo abierta
- **WHEN** `RECEPCION` o `ADMIN` invoca `DELETE /vehiculos/{id}` sobre un vehículo que tiene una orden en un estado con `es_final = False`
- **THEN** el sistema impide la baja lógica y responde HTTP `409 Conflict` (`RN-16`)

#### Scenario: Baja de vehículo inexistente o ya dado de baja
- **WHEN** se invoca `DELETE /vehiculos/{id}` sobre un identificador inexistente o un vehículo que ya posee `borrado_en IS NOT NULL`
- **THEN** el sistema responde HTTP `404 Not Found`

### Requirement: Autoservicio aislado de vehículos propios del cliente
El sistema MUST exponer `GET /mis-vehiculos` para usuarios autenticados devolviendo exclusivamente los vehículos activos (`borrado_en IS NULL`) pertenecientes a la ficha de cliente vinculada al usuario en sesión (`RN-17`).

#### Scenario: Consulta de vehículos propios por cliente autenticado
- **WHEN** un cliente autenticado consulta `GET /mis-vehiculos`
- **THEN** el sistema responde HTTP `200 OK` con la lista de vehículos activos cuyo `cliente_id` corresponde al `usuario_id` en sesión, excluyendo vehículos dados de baja y vehículos de otros clientes (`RN-17`)
