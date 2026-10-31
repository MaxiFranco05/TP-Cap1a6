# Spec Delta: ordenes-and-background-tasks

## Purpose

Provee la gestión integral del ciclo de vida operativo de las órdenes de trabajo del taller mecánico, asegurando la consistencia transaccional del inventario, la inmutabilidad de los catálogos e históricos, y la notificación asincrónica en segundo plano.

## ADDED Requirements

### Requirement: Consulta inmutable del catálogo de estados de orden
El sistema SHALL proveer la consulta del catálogo de estados ordenados por su posición para usuarios autenticados, manteniendo la inmutabilidad del catálogo desde la API. Si el catálogo está vacío en la base de datos, cualquier intento de creación de orden SHALL ser rechazado.

#### Scenario: Consulta exitosa del catálogo de estados
- **WHEN** un usuario autenticado realiza una petición `GET /estados-orden`
- **THEN** el sistema responde con HTTP 200 y la lista de estados ordenada por su campo `posicion`, indicando para cada estado si es final o no.

#### Scenario: Rechazo al crear orden con catálogo vacío
- **WHEN** un usuario intenta crear una orden (`POST /ordenes`) pero la tabla `estado_orden` no posee registros cargados
- **THEN** el sistema responde con HTTP 409 Conflict y un mensaje indicando que el catálogo de estados no está inicializado.

### Requirement: Alta y composición de órdenes de trabajo
El sistema SHALL permitir la creación de órdenes de trabajo a personal de `RECEPCION` o `ADMIN`. La orden debe nacer en estado `PENDIENTE` con al menos un ítem y sin repuestos duplicados. Los precios unitarios de cada repuesto SHALL ser leídos de la base de datos y el total de la orden SHALL ser calculado exclusivamente por el servidor.

#### Scenario: Creación exitosa de una orden de trabajo
- **WHEN** un usuario con rol `RECEPCION` o `ADMIN` envía un `POST /ordenes` con un `vehiculo_id` vigente y una lista de ítems con `repuesto_id` y `cantidad`
- **THEN** el sistema responde con HTTP 201 Created con la orden en estado `PENDIENTE`, los ítems creados con su precio unitario copiado del repuesto, el total calculado por el servidor, y la primera fila en `historial_estado_orden` (`desde_estado = None`, `hasta_estado = "PENDIENTE"`).

#### Scenario: Rechazo si se envían campos prohibidos o repuestos duplicados
- **WHEN** el payload de creación de orden contiene campos de precio, total, estado o repuestos repetidos en la lista de ítems
- **THEN** el sistema responde con HTTP 422 Unprocessable Entity rechazando la petición.

#### Scenario: Rechazo si el vehículo o los repuestos no existen o están borrados
- **WHEN** se intenta crear una orden para un `vehiculo_id` o `repuesto_id` inexistente o dado de baja (`borrado_en IS NOT NULL`)
- **THEN** el sistema responde con HTTP 409 Conflict sin crear la orden ni sus ítems.

### Requirement: Máquina de estados e inicio de reparación
El sistema SHALL permitir a un usuario con rol `MECANICO` tomar una orden en estado `PENDIENTE` e iniciar su reparación mediante `POST /ordenes/{id}/iniciar`, asignándose automáticamente como el mecánico responsable de la orden y transicionando el estado a `EN_REPARACION`.

#### Scenario: Inicio exitoso de reparación por mecánico
- **WHEN** un mecánico autenticado envía un `POST /ordenes/{id}/iniciar` sobre una orden en estado `PENDIENTE`
- **THEN** el sistema responde con HTTP 200 OK, actualiza el estado a `EN_REPARACION`, asigna `mecanico_id` al mecánico en sesión y asienta la transición en `historial_estado_orden`.

#### Scenario: Rechazo si el estado actual no permite iniciar
- **WHEN** un mecánico intenta iniciar una orden cuyo estado no es `PENDIENTE` (por ejemplo, `EN_REPARACION`, `TERMINADA` o `CANCELADA`)
- **THEN** el sistema responde con HTTP 409 Conflict.

### Requirement: Terminación de orden y descuento atómico de stock
El sistema SHALL permitir finalizar una orden en estado `EN_REPARACION` al mecánico asignado o a un `ADMIN`. En una única transacción atómica, el sistema SHALL verificar stock suficiente, descontar inventario, registrar movimientos en `movimiento_stock`, marcar la orden como `TERMINADA`, registrar historial y programar aviso con `BackgroundTasks`. Si el stock no alcanza, SHALL revertir toda la operación.

#### Scenario: Terminación exitosa con stock suficiente y background task
- **WHEN** el mecánico asignado o un `ADMIN` envía `POST /ordenes/{id}/terminar` y todos los repuestos cuentan con stock disponible
- **THEN** el sistema confirma la transacción con HTTP 200 OK, descuenta el stock de los repuestos, asienta los movimientos en `movimiento_stock`, cambia el estado a `TERMINADA`, registra el historial y ejecuta en segundo plano la simulación de aviso al cliente (`await asyncio.sleep(0.5)`).

#### Scenario: Rollback atómico si el stock de algún repuesto es insuficiente
- **WHEN** se intenta terminar una orden pero uno o más repuestos tienen stock menor a la cantidad requerida
- **THEN** el sistema revierte completamente la transacción, responde con HTTP 409 Conflict y el stock, movimientos y estado de la orden quedan intactos.

#### Scenario: Rechazo si un mecánico no asignado intenta terminar la orden
- **WHEN** un usuario con rol `MECANICO` diferente al asignado a la orden intenta ejecutar `POST /ordenes/{id}/terminar`
- **THEN** el sistema responde con HTTP 403 Forbidden.

### Requirement: Cancelación de orden con precedencia de permisos
El sistema SHALL permitir cancelar una orden en estado `PENDIENTE` a usuarios con rol `RECEPCION`, `ADMIN` o al cliente dueño del vehículo ingresado. La evaluación de permisos de identidad SHALL preceder estrictamente a la validación del estado de la orden.

#### Scenario: Cancelación exitosa por recepción, admin o dueño del vehículo
- **WHEN** un usuario autorizado (recepción, admin o dueño del vehículo) envía `POST /ordenes/{id}/cancelar` para una orden `PENDIENTE`
- **THEN** el sistema responde con HTTP 200 OK, transiciona el estado a `CANCELADA` y registra el cambio en el historial.

#### Scenario: Precedencia de permisos sobre validación de estado
- **WHEN** un cliente autenticado intenta cancelar una orden que no le pertenece, independientemente del estado de la orden
- **THEN** el sistema responde con HTTP 403 Forbidden antes de comprobar si la orden es o no cancelable.

#### Scenario: Rechazo si la orden ya no está pendiente
- **WHEN** un usuario con permiso intenta cancelar una orden que está en estado `EN_REPARACION` o `TERMINADA`
- **THEN** el sistema responde con HTTP 409 Conflict.

### Requirement: Consultas con precarga y aislamiento de clientes
El sistema SHALL proveer endpoints de consulta paginada (`GET /ordenes`) y detalle (`GET /ordenes/{id}`) con precarga obligatoria mediante `selectinload` de relaciones para evitar consultas N+1. Los clientes autenticados SHALL estar estrictamente aislados, accediendo únicamente a sus órdenes en `GET /mis-ordenes` o al detalle de órdenes de sus propios vehículos.

#### Scenario: Personal del taller consulta listado y filtros
- **WHEN** un usuario con rol `ADMIN`, `RECEPCION` o `MECANICO` solicita `GET /ordenes` con parámetros `estado`, `page` y `size`
- **THEN** el sistema responde con HTTP 200 OK y el envoltorio estándar de paginación `{items, total, page, size, pages}`.

#### Scenario: Cliente consulta sus órdenes propias
- **WHEN** un cliente autenticado solicita `GET /mis-ordenes`
- **THEN** el sistema responde con HTTP 200 OK conteniendo únicamente las órdenes asociadas a vehículos de su propiedad.

#### Scenario: Cliente intenta acceder al detalle de una orden ajena
- **WHEN** un cliente solicita `GET /ordenes/{id}` para una orden que pertenece al vehículo de otro cliente
- **THEN** el sistema responde con HTTP 403 Forbidden.
