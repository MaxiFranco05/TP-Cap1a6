# Funcionalidades

Las funcionalidades del sistema se estructuran por épica y por historia de usuario (formato `US-NNN`), detallando sus criterios de aceptación y las reglas de negocio vinculadas.

---

## Épica 1: Configuración, Ciclo de Vida y Salud

### US-001 — Monitoreo de estado de la aplicación (/health)
**Como** operador de infraestructura o monitor del sistema  
**Quiero** consultar los endpoints `/health/live` y `/health/ready`  
**Para** saber si el proceso está vivo y si la conexión a PostgreSQL está lista para atender tráfico.

**Criterios de Aceptación**:
- [ ] `GET /health/live` responde HTTP 200 inmediatamente sin consultar la base de datos.
- [ ] `GET /health/ready` ejecuta `SELECT 1` sobre la base de datos; si responde con éxito devuelve HTTP 200 `{"status": "ready"}`.
- [ ] Si la base de datos está caída o inaccesible, `GET /health/ready` responde HTTP 503 Service Unavailable.
- [ ] El motor y la fábrica de sesiones se instancian en el `lifespan` ASGI y se disponen con `dispose()` al apagar.

---

## Épica 2: Autenticación y Control de Accesos

### US-002 — Auto-registro web de clientes
**Como** nuevo cliente del taller  
**Quiero** registrarme en el sistema completando mis datos (email, contraseña, nombre, documento, teléfono)  
**Para** acceder a las consultas de mis vehículos y órdenes de trabajo.

**Criterios de Aceptación**:
- [ ] El registro crea el usuario con su password hasheada con bcrypt, le asigna el rol `CLIENTE` vigente y crea su ficha en la tabla `cliente`.
- [ ] Toda la operación corre en una única transacción atómica (Unit of Work). Si falla algo, no queda ninguna fila creada (RN-02).
- [ ] Si el documento o email ya existen, responde HTTP 409 Conflict.
- [ ] Responde HTTP 201 Created.

### US-003 — Inicio de sesión con mitigación de ataques y Cookie HttpOnly
**Como** usuario del sistema (admin, recepcionista, mecánico o cliente)  
**Quiero** iniciar sesión con mis credenciales  
**Para** autenticarme de manera segura sin exponer tokens en el frontend.

**Criterios de Aceptación**:
- [ ] La contraseña se valida con bcrypt fuera del event loop (`to_thread`) y bajo semáforo concurrente.
- [ ] No acepta contraseñas mayores a 72 bytes en los contratos (responde 422, nunca 500).
- [ ] Si fallan 5 intentos consecutivos en 60 segundos para el mismo correo e IP, responde 429 Too Many Requests con cabecera `Retry-After` (RN-08).
- [ ] Si el correo no existe, ejecuta comparación contra un hash ficticio para tardar el mismo tiempo y responder el mismo error genérico (RN-09).
- [ ] El token JWT no viaja en el cuerpo JSON: se setea exclusivamente en una cookie `access_token` con atributos `HttpOnly`, `SameSite=Lax`, `Max-Age` y `Secure` configurable.
- [ ] Responde HTTP 200 con `{"mensaje": "Sesión iniciada", "debe_cambiar_password": bool, "expira_en_segundos": int}`.

### US-004 — Flujo de cambio obligatorio de contraseña
**Como** usuario con contraseña provisoria asignada  
**Quiero** actualizar mi contraseña obligatoriamente  
**Para** desbloquear el resto de las funcionalidades del sistema.

**Criterios de Aceptación**:
- [ ] Mientras `debe_cambiar_password = True`, el intento de consumir rutas del grupo protegido responde HTTP 403 Forbidden (RN-06).
- [ ] El endpoint `POST /auth/cambiar-password` valida la contraseña anterior, hashea la nueva y actualiza `password_cambiada_en` con fecha/hora microsegundos (RN-07).
- [ ] Se emite una nueva cookie válida y las sesiones anteriores quedan invalidadas de inmediato (responden 401).

---

## Épica 3: Administración de Personal y Roles

### US-005 — Asignación y revocación dinámica de roles con autoprotección
**Como** administrador del taller  
**Quiero** crear usuarios de personal y asignarles o revocarles roles con vencimiento opcional  
**Para** controlar las responsabilidades operativas en el taller.

**Criterios de Aceptación**:
- [ ] `POST /usuarios`: Crea personal administrativo/operativo con contraseña provisoria (`debe_cambiar_password = True`).
- [ ] `POST /usuarios/{id}/roles`: Asigna un rol (`ADMIN`, `RECEPCION`, `MECANICO`) con fecha de vencimiento opcional en el futuro con zona horaria (si está en el pasado o sin timezone responde 422).
- [ ] `DELETE /usuarios/{id}/roles/{rol}`: Revoca el rol seteando `revocada_en = NOW()`.
- [ ] Un administrador no puede revocarse su propio rol `ADMIN` (responde 409) (RN-05).
- [ ] No se puede dejar al sistema sin al menos un `ADMIN` vigente activo (responde 409) (RN-05).

---

## Épica 4: Clientes y Flota de Vehículos

### US-006 — Registro y gestión de clientes y vehículos
**Como** recepcionista o administrador  
**Quiero** registrar clientes y sus vehículos  
**Para** poder abrirles órdenes de servicio en el taller.

**Criterios de Aceptación**:
- [ ] `POST /clientes`: Da de alta un cliente sin usuario con documento único (o 409).
- [ ] `POST /clientes/{id}/vehiculos`: Asocia un vehículo con patente única entre vigentes (año entre 1950 y 2100).
- [ ] `DELETE /vehiculos/{id}`: Realiza borrado lógico (`borrado_en = NOW()`). Si tiene órdenes abiertas, rechaza con 409 (RN-16).
- [ ] Si un vehículo se vendió y se dio de baja, otro cliente puede registrarlo nuevamente con la misma patente (RN-01).

### US-007 — Autoservicio de vehículos propios para clientes
**Como** cliente registrado  
**Quiero** consultar `/mis-vehiculos`  
**Para** ver únicamente los autos registrados a mi nombre.

**Criterios de Aceptación**:
- [ ] Responde HTTP 200 con la lista de vehículos asociados al cliente del usuario en sesión.
- [ ] No permite acceder a vehículos pertenecientes a otros clientes (RN-17).

---

## Épica 5: Gestión de Repuestos, Stock y Precios

### US-008 — Catálogo de repuestos y control de inventario
**Como** administrador  
**Quiero** dar de alta repuestos, actualizar descripciones/precios y reponer stock  
**Para** abastecer al taller de los insumos necesarios para las reparaciones.

**Criterios de Aceptación**:
- [ ] `POST /repuestos`: Da de alta repuesto con `stock_inicial`, generando automáticamente un movimiento en `movimiento_stock` ("Stock inicial").
- [ ] `PATCH /repuestos/{id}`: Modifica descripción y/o precio. El campo `stock` está estrictamente prohibido y rechaza con 422 si se envía (RN-14).
- [ ] Si se modifica el precio, se registra obligatoriamente una fila en `historial_precio_repuesto` en la misma transacción (RN-20). Si el precio no cambia, no se inserta fila.
- [ ] `POST /repuestos/{id}/reponer`: Incrementa el stock registrando el movimiento correspondiente.
- [ ] `DELETE /repuestos/{id}`: Borrado lógico (`borrado_en = NOW()`).

---

## Épica 6: Órdenes de Trabajo y Notificaciones

### US-009 — Apertura de órdenes de trabajo
**Como** recepcionista o administrador  
**Quiero** abrir una orden de trabajo indicando el vehículo, la falla y los repuestos a usar  
**Para** coordinar su reparación con el equipo de mecánicos.

**Criterios de Aceptación**:
- [ ] La orden nace obligatoriamente en estado `PENDIENTE` con al menos un ítem y sin repuestos repetidos (RN-10).
- [ ] Los precios se copian de los repuestos al momento del alta y el total se calcula en el servidor. El cliente no envía precios ni total (RN-10).
- [ ] Se crea la primera línea en `historial_estado_orden` con `desde_estado = None` y `hasta_estado = "PENDIENTE"`.

### US-010 — Transición de órdenes (Iniciar y Terminar)
**Como** mecánico  
**Quiero** iniciar una orden pendiente y luego marcarla como terminada  
**Para** reflejar el avance del trabajo y descontar los repuestos consumidos.

**Criterios de Aceptación**:
- [ ] `POST /ordenes/{id}/iniciar`: Un mecánico inicia la orden; pasa a `EN_REPARACION` y el mecánico queda asignado (`mecanico_id`).
- [ ] `POST /ordenes/{id}/terminar`: Solo el mecánico asignado o un admin pueden terminarla (RN-11).
- [ ] Al terminar, en una sola transacción: la orden pasa a `TERMINADA`, se descuenta el stock de cada ítem, se registra un `movimiento_stock` por cada ítem y una línea en `historial_estado_orden` (RN-13).
- [ ] Si no hay stock suficiente de algún repuesto, la transacción hace rollback total y responde 409 (RN-13).
- [ ] Al terminar exitosamente, se agenda un aviso en segundo plano con `BackgroundTasks` (`asyncio.sleep(0.5)`).

### US-011 — Cancelación de órdenes
**Como** recepcionista, administrador o dueño del vehículo  
**Quiero** cancelar una orden pendiente  
**Para** dar de baja una orden que no se llevará a cabo.

**Criterios de Aceptación**:
- [ ] `POST /ordenes/{id}/cancelar`: Solo permitida desde estado `PENDIENTE`.
- [ ] Se verifica primero la identidad y permiso del actor (403 si es un tercero) antes de verificar el estado de la orden (RN-12).
- [ ] Si la orden ya estaba terminada o en otro estado no cancelable, responde 409.

---

## Épica 7: Trazabilidad y Disparadores Inmutables

### US-012 — Tablas de sólo agregado protegidas en PostgreSQL
**Como** auditor del sistema  
**Quiero** asegurar que las tablas históricas no puedan ser alteradas  
**Para** garantizar la integridad forense de stock, precios y estados.

**Criterios de Aceptación**:
- [ ] Cualquier intento de `UPDATE` o `DELETE` directo sobre `historial_estado_orden`, `movimiento_stock` o `historial_precio_repuesto` es abortado por un trigger de base de datos con excepción (RN-15).
- [ ] La tabla `intento_acceso` guarda cada intento de login en una sesión y transacción independiente para que sobreviva a rollbacks (RN-08).
