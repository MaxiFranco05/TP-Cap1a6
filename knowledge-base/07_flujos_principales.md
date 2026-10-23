# Flujos Principales

Este documento describe los flujos de interacción clave extremo a extremo, detallando componentes involucrados, interacciones transaccionales y manejo de excepciones.

---

## Flujo 1: Inicio de Sesión y Control de Seguridad

```mermaid
sequenceDiagram
    autonumber
    actor Cliente as Cliente HTTP
    participant Router as Auth Router
    participant Service as Auth Service
    participant IndepSession as Sesión Independiente
    participant DB as PostgreSQL
    participant Bcrypt as ThreadPool (Bcrypt)

    Cliente->>Router: POST /auth/login {email, password}
    Router->>Service: autenticar(email, password, ip)
    
    Service->>IndepSession: Contar intentos fallidos en últimos 60s
    IndepSession->>DB: SELECT count(*) FROM intento_acceso WHERE email=... AND ip=... AND cuando > NOW()-60s AND exito=false
    DB-->>IndepSession: conteo
    
    alt conteo >= 5
        Service-->>Router: Error RateLimit (429)
        Router-->>Cliente: 429 Too Many Requests (Retry-After)
    else conteo < 5
        Service->>DB: Buscar usuario por email
        alt usuario no existe
            Service->>Bcrypt: to_thread(bcrypt.checkpw, dummy_hash)
            Bcrypt-->>Service: false
            Service->>IndepSession: Registrar intento_acceso(exito=false)
            IndepSession->>DB: INSERT INTO intento_acceso; COMMIT
            Service-->>Router: Credenciales inválidas (401)
            Router-->>Cliente: 401 Unauthorized (mismo mensaje genérico)
        else usuario existe y activo
            Service->>Bcrypt: to_thread(bcrypt.checkpw, user.password_hash)
            Bcrypt-->>Service: resultado
            alt password incorrecta
                Service->>IndepSession: Registrar intento_acceso(exito=false)
                IndepSession->>DB: INSERT INTO intento_acceso; COMMIT
                Service-->>Router: Credenciales inválidas (401)
                Router-->>Cliente: 401 Unauthorized
            else password correcta
                Service->>IndepSession: Registrar intento_acceso(exito=true)
                IndepSession->>DB: INSERT INTO intento_acceso; COMMIT
                Service->>Service: Generar JWT (sub, iat, exp, roles_informativos)
                Service-->>Router: Token + debe_cambiar_password
                Router-->>Cliente: 200 OK + Set-Cookie: access_token=...; HttpOnly; SameSite=Lax
            end
        end
    end
```

---

## Flujo 2: Auto-registro Atómico del Cliente (RN-02)

**Disparador**: Petición pública a `POST /auth/registro`.  
**Actor**: Visitante web sin cuenta.

1. **Router**: Recibe el payload `RegistroClienteRequest`, valida tipos y rechaza campos extras (`extra="forbid"`). Pasa el control al servicio con el Unit of Work.
2. **Service**:
   - Hashea la contraseña con `asyncio.to_thread(bcrypt.hashpw)` **antes** de abrir la transacción, para no retener conexiones de la base de datos durante el cómputo intensivo de CPU.
   - Abre el Unit of Work con `async with uow:`.
   - Verifica que el `email` no exista en `usuario` (o captura colisión de clave única).
   - Verifica que el `documento` no exista en `cliente` (si existe, responde **409 Conflict** y no se asocia).
   - Inserta `usuario` (con `activo = True`, `debe_cambiar_password = False`).
   - Inserta `asignacion_rol` vinculando al usuario con el rol `CLIENTE`.
   - Inserta ficha `cliente` vinculada al `usuario_id` generado.
3. **Unit of Work**:
   - Al salir del bloque `async with`, ejecuta `await session.commit()`.
   - Si ocurre cualquier excepción (ej. colisión de unicidad), ejecuta `await session.rollback()`.
4. **Respuesta**: HTTP 201 Created con el resumen del perfil creado (sin `password_hash`).

---

## Flujo 3: Ciclo de Vida de una Orden de Trabajo

```
[RECEPCIÓN / ADMIN]               [MECÁNICO]                     [MECÁNICO / ADMIN]
POST /ordenes             POST /ordenes/{id}/iniciar         POST /ordenes/{id}/terminar
     │                                 │                                  │
     ▼                                 ▼                                  ▼
┌──────────────┐              ┌──────────────────┐               ┌────────────────┐
│  PENDIENTE   │ ───────────► │  EN_REPARACION   │ ────────────► │   TERMINADA    │
└──────┬───────┘              └──────────────────┘               └────────────────┘
       │                                                                  │
       │ POST /ordenes/{id}/cancelar                                      │ Evento BackgroundTasks
       │ [Recepción, Admin o Dueño]                                       ▼
       ▼                                                          Aviso simulado al cliente
┌──────────────┐                                                  (asyncio.sleep(0.5))
│  CANCELADA   │
└──────────────┘
```

### Paso a paso: Terminar Orden (RN-13)
1. **Petición**: `POST /ordenes/{id}/terminar` por mecánico asignado o admin.
2. **Apertura de UoW**: `async with uow:`
   - Lee la orden con carga anticipada de ítems y repuestos asociados (`selectinload`).
   - Valida que el estado actual sea `EN_REPARACION` (si no, **409 Conflict**).
   - Valida que quien ejecuta sea el mecánico asignado o un usuario con rol `ADMIN` (si no, **403 Forbidden**).
   - Itera cada `item_orden`:
     - Consulta el repuesto correspondiente.
     - Verifica disponibilidad: `repuesto.stock >= item.cantidad`. Si no alcanza, lanza `StockInsuficienteException` (aborta el bloque, UoW hace rollback y responde **409 Conflict**).
     - Actualiza `repuesto.stock -= item.cantidad`.
     - Inserta fila en `movimiento_stock` con `cantidad = -item.cantidad`, `motivo = "Consumo orden #{id}"` y `usuario_id`.
   - Actualiza estado de la orden: `orden.estado = "TERMINADA"`.
   - Inserta fila en `historial_estado_orden`: `desde_estado = "EN_REPARACION"`, `hasta_estado = "TERMINADA"`.
3. **Commit**: Se confirman todas las operaciones en un solo commit atómico de PostgreSQL.
4. **Post-commit**: Una vez confirmada la transacción, se encola la tarea en `BackgroundTasks` para simular la notificación al cliente (`await asyncio.sleep(0.5)`).

---

## Flujo 4: Cambio Obligatorio de Contraseña y Revocación de Sesiones

1. **Estado Inicial**: Usuario creado por un admin con clave temporal posee `debe_cambiar_password = True`.
2. **Petición Bloqueada**: Al intentar consumir cualquier ruta de negocio (ej. `GET /mis-vehiculos`), la dependencia de autorización del grupo protegido detecta la bandera y corta la ejecución devolviendo HTTP **403 Forbidden**.
3. **Ejecución del Cambio**: El usuario invoca `POST /auth/cambiar-password` con `{password_actual, password_nueva}`:
   - Se valida la clave actual con bcrypt.
   - Se hashea la nueva clave con bcrypt fuera del event loop.
   - Se obtiene la marca de tiempo actual `now = datetime.now(timezone.utc)`.
   - Se actualizan `password_hash = nuevo_hash`, `debe_cambiar_password = False` y `password_cambiada_en = now`.
   - Se emite una nueva cookie JWT con `iat` recién generado (`iat >= now`).
4. **Resultado**: La nueva cookie permite el acceso normal. Cualquier sesión previa cuyo `iat < password_cambiada_en` será rechazada con HTTP **401 Unauthorized** (RN-07).
