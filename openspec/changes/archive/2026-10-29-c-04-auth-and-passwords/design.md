# Design: C-04 Auth and Passwords (`c-04-auth-and-passwords`)

## Context

El proyecto ya cuenta con la configuración tipada (`app/core/config.py`), el ciclo de vida ASGI que inicializa `app.state.engine`, `app.state.session_factory` y `app.state.dummy_hash` (`main.py`), los 13 modelos SQLModel y migraciones Alembic (`C-02`), el patrón `BaseRepository` + `UnitOfWork` con traducción de errores SQL (`C-03`), y las dependencias de lectura JWT/RBAC en `app/core/dependencies.py` introducidas junto con el módulo de clientes (`C-06`).

Falta implementar la capa criptográfica y de sesión (`app/core/security.py`) y el módulo de autenticación y usuarios (`app/modules/usuarios/`) para cubrir los casos oficiales `C-03` a `C-08` y las reglas de negocio `RN-02`, `RN-06`, `RN-07`, `RN-08` y `RN-09`. Ver `proposal.md` para la motivación completa.

## Goals / Non-Goals

**Goals:**
- Desacoplar el hashing y la verificación `bcrypt` del *event loop* mediante `asyncio.to_thread` y `asyncio.Semaphore(settings.BCRYPT_MAX_CONCURRENCY)`.
- Garantizar atomicidad transaccional en el auto-registro (`POST /auth/registro`) creando `Usuario`, `AsignacionRol`, `Cliente` y `EventoSeguridad` en un mismo `UnitOfWork` tras calcular el hash fuera de la transacción.
- Registrar cada intento de login (`exito=True` o `exito=False`) desde una sesión y transacción independiente con `commit()` inmediato para que los fallos persistan aunque la petición devuelva `401`.
- Asegurar que el cambio de contraseña (`POST /auth/cambiar-password`) invalide en el acto cualquier cookie previa comparando `iat` con precisión de microsegundos contra `password_cambiada_en`, incluso cuando el login y el cambio ocurren dentro del mismo milisegundo en pruebas automatizadas sobre Windows.

**Non-Goals:**
- Endpoints administrativos de alta de personal (`POST /usuarios`), gestión dinámica de roles (`/usuarios/{id}/roles`) y consulta de eventos (`GET /eventos`), los cuales corresponden al change `C-05` (`rbac-authorization-and-isolation`).

## Decisions

### 1. Concurrencia de `bcrypt` y límite de 72 bytes UTF-8 (`app/core/security.py` + `schemas.py`)
- **Decisión**: Implementar en `app/core/security.py` un semáforo asincrónico por configuración (`asyncio.Semaphore(settings.BCRYPT_MAX_CONCURRENCY)`) que envuelve cada llamada a `asyncio.to_thread(bcrypt.hashpw, ...)` y `asyncio.to_thread(bcrypt.checkpw, ...)`. Validar `len(v.encode("utf-8")) <= 72` tanto en un validador Pydantic reutilizable en `RegistroClienteRequest`, `LoginRequest` y `CambiarPasswordRequest` (para responder HTTP `422`) como defensivamente en `hash_password` / `verify_password`.
- **Por qué**: `bcrypt` es intensivo en CPU (~100-300 ms por operación) y a partir de `bcrypt 4.x/5.x` lanza `ValueError` si la entrada supera los 72 bytes UTF-8 (p. ej., 40 letras `ñ` ocupan 80 bytes). Validar en Pydantic transforma ese caso borde en un `422 Unprocessable Entity` controlado (Regla Dura #6).
- **Alternativas descartadas**: Validar únicamente `max_length=72` en caracteres sobre el `str` de Pydantic (falla con caracteres multibyte UTF-8 que superan los 72 bytes con menos de 72 caracteres).

### 2. Sesión independiente para `intento_acceso` y cálculo de ventana deslizante (`RN-08`)
- **Decisión**:
  1. En `POST /auth/login`, el registro en `intento_acceso` se ejecuta mediante una sesión propia abierta fuera del `UnitOfWork` de la petición y confirmada inmediatamente con `await indep_session.commit()`. Para mantener compatibilidad total tanto con ejecución real (`request.app.state.session_factory`) como con tests que inyectan u sobreescriben `get_session`, proveer una dependencia `get_independent_session(request)` / fábrica inyectable en `UsuariosService` que utilice `request.app.state.session_factory` o la sesión provista por `dependency_overrides`, documentando explícitamente en un comentario por qué esta escritura es la única del sistema que confirma su propia transacción.
  2. En `IntentoAccesoRepository.count_recent_failures(email, ip, since)`, consultar en SQL el timestamp del último intento exitoso (`MAX(cuando) WHERE exito = True AND cuando >= since`) y contar únicamente las filas con `exito = False` cuyo `cuando` sea mayor que ` COALESCE(ultimo_exito, since)`.
- **Por qué**: Cumple exactamente `RN-08` (*"Un login correcto reinicia la cuenta: los fallos anteriores siguen en la tabla, pero dejan de contar"*) en una consulta indexada sobre `ix_intento_acceso_email_ip_cuando`, sin borrar historial y sin invocar `bcrypt` cuando el conteo alcanza 5.
- **Alternativas descartadas**: Borrar o actualizar filas en `intento_acceso` al iniciar sesión (viola la preservación del historial de accesos exigida en `RN-08`).

### 3. Precisión de microsegundos e invalidación monotónica en `POST /auth/cambiar-password` (`RN-07`)
- **Decisión**:
  1. Emitir el claim `iat` en `create_access_token` como `float(now.timestamp())` sin truncar a entero.
  2. Al ejecutar `POST /auth/cambiar-password`, calcular `now_ts = datetime.now(timezone.utc).timestamp()`. Si el token actual de la petición posee un claim `iat` y `now_ts <= float(token_iat)` (situación posible en tests automatizados en Windows donde dos peticiones consecutivas ocurren en el mismo *tick* del reloj del sistema), fijar `now_ts = float(token_iat) + 1e-6` (1 microsegundo después del token anterior).
  3. Reconstruir `cambio_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)` a partir del mismo `float` IEEE 754, asignarlo a `user.password_cambiada_en = cambio_dt` y emitir el nuevo JWT con `iat = cambio_dt.timestamp()`.
- **Por qué**: `app/core/dependencies.py` reconstruye `iat_dt = datetime.fromtimestamp(float(iat_raw), tz=timezone.utc)` y verifica `if iat_dt < user.password_cambiada_en`. Al alinear `cambio_dt` con la representación `float` exacta y garantizar que sea estrictamente mayor en al menos `1 µs` al `iat` del token anterior:
  - El token viejo cumple `old_iat_dt < user.password_cambiada_en` de forma determinista (responde `401` sin necesidad de `sleep`).
  - El token nuevo cumple `new_iat_dt == user.password_cambiada_en` (nunca sufre pérdida de 1 microsegundo por redondeo IEEE 754, respondiendo `200 OK`).
- **Alternativas descartadas**: Truncar `iat` a segundos enteros (haría fallar el caso oficial `C-08` cuando el cambio ocurre en el mismo segundo que el login) o agregar `asyncio.sleep()` artificial en el endpoint.

### 4. Estructura de `GET /auth/yo` y separación de routers en `app/modules/usuarios/router.py`
- **Decisión**:
  - `GET /auth/yo` extrae el usuario mediante `Depends(get_current_user)` (permitiendo el acceso con `debe_cambiar_password = True`), decodifica los roles del token (`roles_token`) y consulta en tiempo real los roles vigentes en `asignacion_rol` (`roles`), devolviendo `UsuarioResponse`.
  - Definir `auth_router = APIRouter(prefix="/auth", tags=["auth"])` en `app/modules/usuarios/router.py` (exportado también como `router` para el grupo abierto en `main.py`), dejando listo el módulo para que `C-05` agregue el router protegido de administración de usuarios y eventos.

## Risks / Trade-offs

- **[Risk] Redondeo de punto flotante IEEE 754 al convertir `datetime` ↔ `float` en `iat`** → **Mitigation**: Derivar `password_cambiada_en` mediante `datetime.fromtimestamp(float_ts, tz=timezone.utc)` y reutilizar ese mismo `float_ts` como `iat` del nuevo JWT.
- **[Risk] Bloqueo de conexión PostgreSQL durante el hashing `bcrypt` en `POST /auth/registro` y `POST /auth/cambiar-password`** → **Mitigation**: Ejecutar siempre `await hash_password(...)` y `await verify_password(...)` **antes** de entrar al bloque `async with self.uow:`.
- **[Risk] Contención de hilos ante ráfagas de login concurrentes** → **Mitigation**: El chequeo de rate limit (`RN-08`) se ejecuta antes de `bcrypt`, y `bcrypt` está protegido por `asyncio.Semaphore(settings.BCRYPT_MAX_CONCURRENCY)`.
