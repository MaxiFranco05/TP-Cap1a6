# Proposal: C-04 Auth and Passwords (`c-04-auth-and-passwords`)

## Why

El taller mecánico necesita autenticar tanto a clientes (que pueden auto-registrarse en la web) como al personal operativo y administrativo, protegiendo las credenciales y las sesiones contra ataques de fuerza bruta, enumeración de usuarios por tiempo de respuesta (*timing attacks*), robo de tokens por XSS y agotamiento del bucle de eventos asincrónico durante el cálculo de hashes `bcrypt`. Además, debe garantizar el cambio obligatorio de contraseñas provisorias (`RN-06`) y la invalidación inmediata de sesiones anteriores con precisión de microsegundos al cambiar la contraseña (`RN-07`).

## What Changes

- **Módulo criptográfico y de sesión (`app/core/security.py`)**:
  - Hashing y verificación de contraseñas con `bcrypt` ejecutados fuera del *event loop* mediante `asyncio.to_thread`, acotados por un semáforo asincrónico (`asyncio.Semaphore(settings.BCRYPT_MAX_CONCURRENCY)`) y costo configurable (`settings.BCRYPT_ROUNDS`).
  - Validación estricta del límite de 72 bytes en UTF-8 para contraseñas (`len(password.encode("utf-8")) <= 72`).
  - Uso de hash ficticio precalculado (`dummy_hash`) para mitigar *timing attacks* cuando el email consultado no existe (`RN-09`).
  - Emisión y decodificación de tokens JWT (`HS256`) con claims `sub` (`str(user.id)`), `iat` en punto flotante con precisión de microsegundos (sin truncar a segundos), `exp` y `roles` informativos.
  - Utilidades `set_auth_cookie` y `clear_auth_cookie` para gestionar la cookie `access_token` (`HttpOnly`, `SameSite=Lax`, `Max-Age=settings.JWT_EXPIRATION_SECONDS`, `Secure=settings.COOKIE_SECURE`, `Path=/`) sin exponer jamás el JWT en el cuerpo JSON.
- **Esquemas Pydantic estrictos (`app/modules/usuarios/schemas.py`)**:
  - `RegistroClienteRequest`, `LoginRequest` y `CambiarPasswordRequest` con `ConfigDict(extra="forbid")` y validación de longitud en bytes UTF-8 (`1..72` bytes) en todos los campos de contraseña (rechazando excesos con HTTP `422`).
  - `LoginResponse` (`mensaje`, `debe_cambiar_password`, `expira_en_segundos`) y `UsuarioResponse` (`id`, `email`, `nombre`, `activo`, `debe_cambiar_password`, `roles`, `roles_token`, excluyendo `password_hash`).
- **Repositorios y Unit of Work de Usuarios (`app/modules/usuarios/repository.py`, `app/modules/usuarios/unit_of_work.py`, `app/core/unit_of_work.py`)**:
  - `UsuarioRepository`, `AsignacionRolRepository`, `IntentoAccesoRepository` y `EventoSeguridadRepository` extendiendo `BaseRepository` (solo `flush()`, nunca `commit()`).
  - Integración en `UnitOfWork` y `UsuariosUnitOfWork` compartiendo la misma `AsyncSession` con `ClienteRepository` para transacciones multi-entidad.
- **Servicios y Endpoints de Autenticación (`app/modules/usuarios/service.py`, `app/modules/usuarios/router.py`, `main.py`)**:
  - `POST /auth/registro`: calcula el hash `bcrypt` antes de abrir la transacción y, dentro de un único bloque `UnitOfWork`, verifica unicidad de `email` y `documento` (`409 Conflict` si ya existen, sin apropiarse de clientes previos), inserta `Usuario`, `AsignacionRol(rol=CLIENTE)`, `Cliente` y `EventoSeguridad` de forma atómica (`RN-02`).
  - `POST /auth/login`: verifica ventana de 5 intentos fallidos consecutivos en los últimos 60 segundos para `(email, ip)` respondiendo `429 Too Many Requests` con cabecera `Retry-After: 60` sin invocar `bcrypt` (`RN-08`); mitiga *timing attacks* verificando contra `dummy_hash` si el correo no existe (`RN-09`); registra cada intento (exitoso o fallido) en `intento_acceso` usando una sesión y transacción independiente con `commit()` inmediato; y en caso exitoso emite la cookie `access_token` y devuelve `LoginResponse` (`200 OK`).
  - `POST /auth/logout`: elimina la cookie `access_token` (`Max-Age=0`) y responde `200 OK`.
  - `GET /auth/yo`: devuelve el perfil del usuario autenticado junto con sus roles vigentes en base de datos (`roles`) y los roles declarados en el JWT (`roles_token`), accesible incluso con `debe_cambiar_password = True` (`RN-06`).
  - `POST /auth/cambiar-password`: verifica `password_actual` (`401` si no coincide), hashea `password_nueva` fuera de la transacción, actualiza `password_hash`, `debe_cambiar_password = False` y `password_cambiada_en` con precisión de microsegundos en UTC, registra `EventoSeguridad` y emite una nueva cookie `access_token` cuyo `iat >= password_cambiada_en`, invalidando de inmediato toda cookie anterior (`RN-07`).
  - Montaje del router de autenticación en el grupo abierto (`router_abierto`) de `main.py`.

## Capabilities

### New Capabilities
- `auth-and-passwords`: Autenticación por cookie `HttpOnly`, hashing `bcrypt` fuera del bucle de eventos con semáforo y límite de 72 bytes UTF-8, auto-registro atómico de clientes (`RN-02`), login con mitigación de *timing attacks* (`RN-09`) y *rate limiting* por ventana deslizante en sesión independiente (`RN-08`), consulta de perfil `/auth/yo` y cambio de contraseña con invalidación instantánea de sesiones previas por microsegundos (`RN-06`, `RN-07`).

### Modified Capabilities
<!-- No existing capability requirements are modified. -->

## Impact

- **Nuevos archivos**:
  - `app/core/security.py`
  - `app/modules/usuarios/schemas.py`
  - `app/modules/usuarios/repository.py`
  - `app/modules/usuarios/unit_of_work.py`
  - `app/modules/usuarios/service.py`
  - `app/modules/usuarios/router.py`
  - `tests/test_auth_passwords.py`
- **Archivos modificados**:
  - `app/core/unit_of_work.py` (registro de repositorios del módulo `usuarios` en `UnitOfWork.__aenter__`)
  - `main.py` (inclusión del router de `/auth` dentro de `router_abierto`)
