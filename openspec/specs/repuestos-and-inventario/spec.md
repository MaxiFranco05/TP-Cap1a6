# repuestos-and-inventario Specification

## Purpose

Gobierna la administración del catálogo de repuestos y su inventario en el taller mecánico, asegurando unicidad parcial de códigos vigentes (`RN-01`), mutación de existencias centralizada por movimientos (`RN-14`), trazabilidad transaccional obligatoria ante variaciones de precio (`RN-20`), búsqueda paginada segura y preservación inmutable de historiales (`RN-15`, `RN-16`).

## Requirements

### Requirement: Alta de repuestos con código único vigente y movimiento de stock inicial
El sistema MUST permitir a usuarios con rol `ADMIN` registrar repuestos mediante `POST /repuestos` validando esquemas estrictos (`extra="forbid"`), exigiendo `precio > 0` en `Decimal` y `stock_inicial >= 0`. El código MUST ser único entre repuestos activos (`RN-01`), respondiendo HTTP `409 Conflict` ante duplicados activos y permitiendo reutilizar códigos dados de baja. Si `stock_inicial > 0`, MUST registrar un movimiento `"Stock inicial"` en la misma transacción (`RN-14`).

#### Scenario: Alta exitosa con stock inicial positivo genera movimiento
- **WHEN** un usuario con rol `ADMIN` envía `POST /repuestos` con `codigo`, `descripcion`, `precio = "8500.00"` y `stock_inicial = 10`
- **THEN** el sistema persiste el repuesto con `stock = 10` e inserta atómicamente una fila en `movimiento_stock` con `cantidad = 10`, `motivo = "Stock inicial"` y `usuario_id` del administrador, respondiendo HTTP `201 Created`

#### Scenario: Alta exitosa con stock inicial cero no genera movimiento
- **WHEN** un usuario con rol `ADMIN` envía `POST /repuestos` con `stock_inicial = 0`
- **THEN** el sistema persiste el repuesto con `stock = 0` sin insertar filas en `movimiento_stock` y responde HTTP `201 Created`

#### Scenario: Rechazo por código duplicado activo
- **WHEN** un usuario con rol `ADMIN` envía `POST /repuestos` con un `codigo` que ya pertenece a un repuesto activo (`borrado_en IS NULL`)
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` sin filtrar detalles internos del motor de base de datos (`RN-01`)

#### Scenario: Reutilización de código perteneciente a un repuesto dado de baja
- **WHEN** un repuesto previo con código `"FIL-001"` fue dado de baja lógicamente (`borrado_en IS NOT NULL`) y un `ADMIN` envía `POST /repuestos` con `codigo = "FIL-001"`
- **THEN** el sistema permite crear el nuevo repuesto activo y responde HTTP `201 Created` (`RN-01`)

### Requirement: Mutación de stock exclusiva por movimientos y reposición manual
El sistema MUST alterar el stock de un repuesto únicamente a través de un punto único de escritura que actualice `repuesto.stock` e inserte simultáneamente el registro en `movimiento_stock` dentro de la misma transacción (`RN-14`). El endpoint `POST /repuestos/{id}/reponer` (rol `ADMIN`) MUST incrementar las existencias con `cantidad > 0` y `motivo`, y `PATCH /repuestos/{id}` MUST rechazar con HTTP `422 Unprocessable Entity` cualquier intento de enviar el campo `stock`.

#### Scenario: Reposición manual exitosa incrementa stock y asienta movimiento
- **WHEN** un usuario con rol `ADMIN` envía `POST /repuestos/{id}/reponer` sobre un repuesto activo con `cantidad = 5` y `motivo = "Compra a proveedor"`
- **THEN** el sistema incrementa `repuesto.stock` en `5`, inserta la fila en `movimiento_stock` con `cantidad = 5`, `motivo = "Compra a proveedor"` y `orden_id = null`, y responde HTTP `200 OK` con el repuesto actualizado

#### Scenario: Rechazo de modificación directa de stock mediante PATCH
- **WHEN** un usuario con rol `ADMIN` envía `PATCH /repuestos/{id}` incluyendo el campo `"stock"` en el cuerpo JSON
- **THEN** el sistema rechaza la petición con HTTP `422 Unprocessable Entity` sin modificar el repuesto (`RN-14`)

#### Scenario: Rechazo de reposición con cantidad inválida o repuesto inexistente
- **WHEN** se invoca `POST /repuestos/{id}/reponer` con `cantidad <= 0` o sobre un repuesto inexistente o dado de baja
- **THEN** el sistema responde HTTP `422 Unprocessable Entity` ante cantidad no positiva o HTTP `404 Not Found` si el repuesto activo no existe

### Requirement: Actualización parcial de repuesto y trazabilidad obligatoria de precios
El sistema MUST procesar `PATCH /repuestos/{id}` (rol `ADMIN`) aplicando únicamente los campos enviados en la petición (`exclude_unset=True`). Si el campo `precio` es enviado y difiere del precio vigente, el sistema MUST actualizar `repuesto.precio` e insertar una fila en `historial_precio_repuesto` con `precio_anterior`, `precio_nuevo` y `usuario_id` en la misma transacción (`RN-20`). Si el precio no cambia o no se envía, MUST NOT insertar filas en el historial.

#### Scenario: Cambio efectivo de precio actualiza repuesto y registra historial atómicamente
- **WHEN** un `ADMIN` envía `PATCH /repuestos/{id}` con `{"precio": "9200.00"}` sobre un repuesto cuyo precio actual es `"8500.00"`
- **THEN** el sistema actualiza `repuesto.precio` a `"9200.00"`, inserta en la misma transacción un registro en `historial_precio_repuesto` con `precio_anterior = 8500.00` y `precio_nuevo = 9200.00`, y responde HTTP `200 OK` (`RN-20`)

#### Scenario: Actualización parcial de descripción sin modificar precio no genera historial
- **WHEN** un `ADMIN` envía `PATCH /repuestos/{id}` con `{"descripcion": "Filtro de aceite sintético"}` omitiendo el campo `precio`
- **THEN** el sistema actualiza únicamente `descripcion` preservando el `precio` original sin generar ninguna fila en `historial_precio_repuesto` y responde HTTP `200 OK` (`RN-20`)

#### Scenario: Envío del mismo precio vigente no genera fila redundante en historial
- **WHEN** un `ADMIN` envía `PATCH /repuestos/{id}` con un `precio` numéricamente idéntico al `precio` actual del repuesto
- **THEN** el sistema responde HTTP `200 OK` sin insertar ninguna fila en `historial_precio_repuesto` (`RN-20`)

### Requirement: Búsqueda paginada segura y consulta de repuestos activos
El sistema MUST exponer `GET /repuestos` y `GET /repuestos/{id}` para usuarios con rol `ADMIN`, `RECEPCION` o `MECANICO` sobre repuestos activos (`borrado_en IS NULL`). `GET /repuestos` MUST soportar paginación (`page`, `size`) y búsqueda opcional `q` por subcadena en `descripcion` mediante parámetros ligados, calculando `total` y `pages` con el mismo filtro activo y rechazando con HTTP `422` páginas fuera de rango o tamaños inválidos.

#### Scenario: Listado paginado y filtrado por descripción con parámetros ligados
- **WHEN** un usuario con rol `ADMIN`, `RECEPCION` o `MECANICO` consulta `GET /repuestos?q=freno&page=1&size=2`
- **THEN** el sistema responde HTTP `200 OK` con la estructura `{items, total, page, size, pages}` conteniendo sólo repuestos activos cuya `descripcion` coincida insensiblemente a mayúsculas con `"freno"` y calculando `total` sobre ese mismo subconjunto

#### Scenario: Prevención de inyección SQL en parámetro de búsqueda q
- **WHEN** se consulta `GET /repuestos?q=' OR '1'='1`
- **THEN** el sistema evalúa la cadena como parámetro ligado literal sin interpolar SQL, devolviendo HTTP `200 OK` con `items = []`, `total = 0` y `pages = 1`

#### Scenario: Rechazo por página fuera de rango respecto al total filtrado
- **WHEN** se consulta `GET /repuestos?q=freno&page=2&size=10` existiendo sólo 1 repuesto coincidente (`pages = 1`) o con `size > 100`
- **THEN** el sistema rechaza la consulta con HTTP `422 Unprocessable Entity`

#### Scenario: Consulta individual de repuesto activo por identificador
- **WHEN** un usuario con rol `ADMIN`, `RECEPCION` o `MECANICO` consulta `GET /repuestos/{id}`
- **THEN** el sistema devuelve HTTP `200 OK` con los datos del repuesto si está activo, o HTTP `404 Not Found` si no existe o fue dado de baja lógicamente

### Requirement: Baja lógica de repuestos y conservación de historiales auditables
El sistema MUST ejecutar la baja lógica en `DELETE /repuestos/{id}` (rol `ADMIN`) asignando `borrado_en` con timestamp UTC y respondiendo HTTP `204 No Content` (`404` si no existe o ya fue dado de baja). Los registros históricos en `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios` (rol `ADMIN`) MUST conservarse y seguir siendo consultables aun después de la baja lógica del repuesto (`RN-16`).

#### Scenario: Baja lógica exitosa oculta el repuesto de listados y consultas activas
- **WHEN** un usuario con rol `ADMIN` invoca `DELETE /repuestos/{id}` sobre un repuesto activo
- **THEN** el sistema asigna `borrado_en` con marca temporal UTC, responde HTTP `204 No Content`, y el repuesto deja de aparecer en `GET /repuestos` y `GET /repuestos/{id}` (`404 Not Found`)

#### Scenario: Consulta de movimientos e historial de precios de un repuesto incluso tras su baja lógica
- **WHEN** un usuario con rol `ADMIN` consulta `GET /repuestos/{id}/movimientos` o `GET /repuestos/{id}/precios` de un repuesto existente (activo o dado de baja lógicamente)
- **THEN** el sistema responde HTTP `200 OK` con la lista completa ordenada cronológicamente de movimientos de stock o variaciones de precio (`RN-16`)

#### Scenario: Consulta de historiales sobre repuesto inexistente devuelve 404
- **WHEN** un usuario con rol `ADMIN` consulta `GET /repuestos/{id}/movimientos` o `GET /repuestos/{id}/precios` con un `id` que nunca fue registrado
- **THEN** el sistema responde HTTP `404 Not Found`

### Requirement: Control de acceso por roles e inmutabilidad de tablas de sólo agregado
El sistema MUST restringir las operaciones de escritura (`POST`, `PATCH`, `DELETE`, `/reponer`) y de auditoría (`/movimientos`, `/precios`) exclusivamente al rol `ADMIN`, respondiendo HTTP `403 Forbidden` a otros roles. Asimismo, las tablas `movimiento_stock`, `historial_precio_repuesto` e `historial_estado_orden` MUST rechazar cualquier `UPDATE` o `DELETE` directo mediante disparadores de base de datos (`RN-15`).

#### Scenario: Personal de recepción y mecánicos tienen acceso de sólo lectura al catálogo activo
- **WHEN** un usuario con rol `RECEPCION`, `MECANICO` o `CLIENTE` invoca `POST /repuestos`, `PATCH /repuestos/{id}`, `DELETE /repuestos/{id}`, `POST /repuestos/{id}/reponer`, `GET /repuestos/{id}/movimientos` o `GET /repuestos/{id}/precios`
- **THEN** el sistema rechaza la petición con HTTP `403 Forbidden`

#### Scenario: Disparadores de base de datos rechazan UPDATE y DELETE en tablas históricas
- **WHEN** cualquier proceso o sesión ejecuta una sentencia `UPDATE` o `DELETE` sobre `movimiento_stock`, `historial_precio_repuesto` o `historial_estado_orden`
- **THEN** el disparador PL/pgSQL `trg_<tabla>_solo_agregado` aborta la operación lanzando una excepción de base de datos (`RN-15`)
