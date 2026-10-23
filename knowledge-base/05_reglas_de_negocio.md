# Reglas de Negocio

Este documento formaliza las 20 reglas de negocio oficiales (RN-01 a RN-20) definidas en la especificación del Trabajo Práctico, clasificadas por dominio funcional.

---

## Dominio: Unicidad e Integridad de Entidades (RN-ENT)

### RN-01 — Unicidad con soporte de borrado lógico
- **Enunciado**: El correo de un usuario y el documento de un cliente son únicos en todo el sistema. La patente de un vehículo y el código de un repuesto son únicos estrictamente entre aquellos que **no** están dados de baja (`WHERE borrado_en IS NULL`).
- **Garante esperado**: Restricciones `UNIQUE` estándar e índices únicos parciales en PostgreSQL (`postgresql_where`). Ante conflicto, responde HTTP **409 Conflict** con mensaje propio.
- **Justificación**: Un vehículo vendido o un repuesto discontinuado se da de baja lógicamente sin romper el historial; un nuevo comprador puede registrar la misma patente sin colisión.

### RN-16 — Conservación por borrado lógico y bloqueo de baja
- **Enunciado**: Un vehículo o repuesto dado de baja deja de aparecer en listados y no puede utilizarse en nuevas órdenes de trabajo, pero sus registros históricos se conservan. Un vehículo con órdenes abiertas (aquellas cuyo estado en el catálogo no tiene `es_final = True`) **no puede darse de baja**.
- **Garante esperado**: Lógica en la capa de Servicio con verificación previa; responde **409 Conflict** si tiene órdenes abiertas.

### RN-18 — Intercepción de errores de base de datos
- **Enunciado**: Ningún error de la aplicación devuelve al cliente texto interno de la base de datos ni trazas de excepciones (`IntegrityError`), para no exponer la estructura interna del esquema. Ninguna entrada inválida debe generar un error HTTP **500 Internal Server Error**.
- **Garante esperado**: Traducción estricta de `IntegrityError` y validaciones previas en contratos Pydantic (respondiendo 409, 422 o 400 según corresponda).

---

## Dominio: Autenticación y Gestión de Cuentas (RN-AUTH)

### RN-02 — Auto-registro atómico del cliente
- **Enunciado**: El auto-registro web crea en una única transacción: el usuario, su asignación al rol `CLIENTE` y su ficha de cliente correspondiente. Quedan las tres filas guardadas o no queda ninguna. Si el documento ingresado ya pertenece a un cliente del taller, la operación rechaza con **409 Conflict** y no se apropia de la ficha existente.
- **Garante esperado**: Ejecución dentro de un único bloque transaccional del `UnitOfWork`.

### RN-06 — Restricción por cambio obligatorio de contraseña
- **Enunciado**: Mientras un usuario tenga la bandera `debe_cambiar_password = True`, únicamente tiene permitido consumir las rutas de autenticación (`/auth/*`) y las rutas de verificación de salud (`/health/*`).
- **Garante esperado**: Dos grupos de rutas en `main.py` (abierto vs protegido); middleware o dependencia en el grupo protegido que responde **403 Forbidden**.

### RN-07 — Invalidación inmediata de sesiones previas al cambiar clave
- **Enunciado**: Al concretar un cambio de contraseña, todas las sesiones y tokens emitidos con anterioridad pierden validez de inmediato, incluso si fueron emitidos en el mismo segundo que el cambio. El token entregado por la propia petición de cambio de clave se mantiene válido.
- **Garante esperado**: Comparación precisa de `iat` (con microsegundos, sin truncar a enteros) contra `password_cambiada_en`; responde **401 Unauthorized** para sesiones anteriores.

### RN-08 — Límite de intentos fallidos (Anti-Brute Force)
- **Enunciado**: Tras registrarse 5 intentos fallidos consecutivos para el mismo correo desde la misma dirección IP en una ventana de 60 segundos, el endpoint de login responde inmediatamente **429 Too Many Requests** con la cabecera `Retry-After`, sin verificar la contraseña. Un login exitoso reinicia el conteo de fallos activos.
- **Garante esperado**: Consulta de conteo sobre la tabla `intento_acceso`.

### RN-09 — Mitigación de Timing Attacks en Login
- **Enunciado**: El login responde exactamente el mismo mensaje genérico de error y demora un tiempo equivalente tanto si el correo existe como si no existe en el sistema.
- **Garante esperado**: Verificación contra un hash ficticio precalculado cuando el usuario no es encontrado en la base de datos.

---

## Dominio: Autorización y Roles (RN-ROL)

### RN-03 — Asignación única por rol
- **Enunciado**: Un usuario puede tener asignados múltiples roles diferentes, pero a lo sumo una única asignación abierta y vigente por cada rol (`WHERE revocada_en IS NULL`).
- **Garante esperado**: Índice único parcial en `asignacion_rol(usuario_id, rol)`; responde **409 Conflict** ante duplicación.

### RN-04 — Consulta de roles en tiempo real
- **Enunciado**: Los permisos de acceso se evalúan consultando en cada petición los roles vigentes guardados en la base de datos. Los roles incluidos en el payload del token JWT son meramente informativos.
- **Garante esperado**: Dependencia FastAPI `requiere_rol` que realiza consulta a la tabla `asignacion_rol`.

### RN-05 — Autoprotección de administradores
- **Enunciado**: Un administrador no puede revocarse a sí mismo su propio rol `ADMIN`, y el sistema nunca puede quedar sin administradores vigentes activos.
- **Garante esperado**: Comprobación en la capa de Servicio; responde **409 Conflict** si se intenta violar la regla.

### RN-17 — Aislamiento de datos de clientes (/mis-*)
- **Enunciado**: Las rutas de autoservicio para clientes (`/mis-vehiculos`, `/mis-ordenes`) exigen autenticación y restringen la visibilidad estrictamente a los vehículos propios del cliente y las órdenes asociadas a dichos vehículos.
- **Garante esperado**: Filtrado por el `cliente_id` del usuario autenticado; intento de acceso a recursos ajenos responde **403 Forbidden**.

---

## Dominio: Órdenes de Trabajo y Estados (RN-ORD)

### RN-10 — Creación y composición de órdenes
- **Enunciado**: Una orden de trabajo nace obligatoriamente en estado `PENDIENTE`, con al menos un ítem de repuesto y sin repuestos duplicados. El precio unitario de cada ítem se copia directamente del repuesto en ese instante, y el total de la orden lo calcula exclusivamente el servidor. Ni los precios ni el total pueden viajar en el payload de creación.
- **Garante esperado**: Validación en DTO de entrada (`extra="forbid"`) y cálculo en el Servicio.

### RN-11 — Máquina de estados finitos para órdenes
- **Enunciado**: Las transiciones permitidas son exclusivamente:
  - `PENDIENTE` → `EN_REPARACION`: Iniciada por un mecánico, quien queda registrado como mecánico asignado.
  - `EN_REPARACION` → `TERMINADA`: Finalizada por el mecánico asignado o por un administrador.
  - `PENDIENTE` → `CANCELADA`: Cancelación de la orden.
- **Garante esperado**: Control de transiciones en el Servicio; responde **409 Conflict** ante transiciones no permitidas.

### RN-12 — Permisos de cancelación de órdenes
- **Enunciado**: Pueden cancelar una orden pendiente: el personal de recepción, un administrador o el cliente dueño del vehículo ingresado. Los permisos de identidad se evalúan antes que el estado de la orden (respondiendo **403 Forbidden** antes que **409 Conflict**).
- **Garante esperado**: Orden de evaluación en el Servicio del módulo `ordenes`.

### RN-19 — Inmutabilidad del catálogo de estados
- **Enunciado**: Los estados válidos corresponden a las filas de la tabla catálogo `estado_orden`. Este catálogo se consulta desde la API pero no puede editarse desde ella. Si la tabla estuviera vacía, el intento de crear una orden responde **409 Conflict** con mensaje propio explicativo.
- **Garante esperado**: Clave foránea en base de datos y repositorio de solo lectura sin métodos `add/update/delete`.

---

## Dominio: Inventario, Stock y Precios (RN-STK)

### RN-13 — Consumo atómico de stock al terminar orden
- **Enunciado**: Al marcar una orden como `TERMINADA`, se descuenta el stock de cada repuesto utilizado, se registra un movimiento de salida por cada ítem y se asienta la línea correspondiente en el historial de estados. Si alguno de los repuestos no cuenta con stock suficiente, se cancela la operación y no queda registrada ninguna escritura.
- **Garante esperado**: Ejecución en un único bloque del `UnitOfWork`; responde **409 Conflict** si falta stock.

### RN-14 — Mutación de stock exclusiva por movimientos
- **Enunciado**: El stock de un repuesto únicamente puede alterarse a través de registros de movimientos: alta con stock inicial, reposición manual y terminación de órdenes de trabajo. Está estrictamente prohibido editar el stock directamente mediante peticiones `PATCH`.
- **Garante esperado**: Contratos Pydantic de actualización que rechazan el campo `stock` (`extra="forbid"`).

### RN-20 — Histórico obligatorio ante cambios de precio
- **Enunciado**: Cada modificación en el precio de un repuesto debe asentar una fila en `historial_precio_repuesto` dentro de la misma transacción. Una petición `PATCH` que modifique otros datos (como la descripción) pero mantenga el precio idéntico **no** debe generar ninguna fila en el historial.
- **Garante esperado**: Verificación en Servicio y transacción atómica en `UnitOfWork`.

---

## Dominio: Trazabilidad y Disparadores (RN-INT)

### RN-15 — Inmutabilidad estricta de tablas de sólo agregado
- **Enunciado**: Las tablas `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` son de **sólo agregado**: ningún usuario ni proceso del sistema puede modificar (`UPDATE`) ni eliminar (`DELETE`) sus registros.
- **Garante esperado**: Disparadores (`TRIGGERS`) a nivel de base de datos en PostgreSQL, instalados mediante migración manual de Alembic, que rechazan cualquier operación de actualización o borrado.
