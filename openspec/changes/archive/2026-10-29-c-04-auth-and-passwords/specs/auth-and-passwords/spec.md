# Spec Delta: Auth and Passwords (`auth-and-passwords`)

## Purpose

Provee la autenticación segura del sistema mediante cookies `HttpOnly`, hashing `bcrypt` desacoplado del bucle de eventos con semáforo de concurrencia y validación de 72 bytes UTF-8, auto-registro transaccional de clientes (`RN-02`), mitigación de *timing attacks* (`RN-09`), limitación de intentos de acceso en sesión independiente (`RN-08`), consulta de identidad (`/auth/yo`) y cambio de contraseña con invalidación inmediata de sesiones previas por microsegundos (`RN-06`, `RN-07`).

## ADDED Requirements

### Requirement: Hashing asincrónico de contraseñas con semáforo y límite de 72 bytes UTF-8
El sistema MUST ejecutar toda operación de hashing y verificación `bcrypt` fuera del bucle de eventos asincrónico mediante `asyncio.to_thread`, acotada por un `asyncio.Semaphore(settings.BCRYPT_MAX_CONCURRENCY)` y costo `settings.BCRYPT_ROUNDS`, y MUST validar en los esquemas de entrada que ninguna contraseña supere los 72 bytes codificados en UTF-8 ni contenga campos extra (`extra="forbid"`).

#### Scenario: Ejecución de bcrypt fuera del event loop bajo semáforo
- **WHEN** el sistema calcula un hash o verifica una contraseña válida de hasta 72 bytes UTF-8
- **THEN** la operación se delega a un hilo separado mediante `asyncio.to_thread` respetando el límite de concurrencia `BCRYPT_MAX_CONCURRENCY` y devuelve un hash verificable sin bloquear el bucle de eventos

#### Scenario: Rechazo de contraseña que supera 72 bytes en UTF-8
- **WHEN** un cliente envía en `POST /auth/registro`, `POST /auth/login` o `POST /auth/cambiar-password` una contraseña cuya representación UTF-8 supera los 72 bytes (por ejemplo, 73 caracteres ASCII o 40 caracteres multibyte `ñ` equivalentes a 80 bytes)
- **THEN** el esquema Pydantic rechaza la petición con HTTP `422 Unprocessable Entity` antes de invocar `bcrypt`, evitando cualquier error `500`

#### Scenario: Rechazo de campos no declarados en esquemas de autenticación
- **WHEN** se envía una petición a `POST /auth/registro`, `POST /auth/login` o `POST /auth/cambiar-password` con atributos adicionales no definidos en el contrato
- **THEN** el sistema rechaza la petición con HTTP `422 Unprocessable Entity`

### Requirement: Auto-registro atómico de clientes web (`POST /auth/registro`)
El sistema MUST permitir el auto-registro de clientes en `POST /auth/registro` calculando el hash `bcrypt` antes de abrir la transacción de base de datos y creando de forma atómica dentro de un único bloque `UnitOfWork` las filas en `usuario`, `asignacion_rol` (`rol = CLIENTE`), `cliente` y `evento_seguridad`, revirtiendo todos los cambios y respondiendo HTTP `409 Conflict` si el `email` o el `documento` ya existen (`RN-02`).

#### Scenario: Auto-registro exitoso de nuevo cliente
- **WHEN** un visitante envía `POST /auth/registro` con `email` libre, `password` válida (<= 72 bytes UTF-8), `nombre`, `documento` libre y `telefono`
- **THEN** el sistema hashea la contraseña fuera de la transacción, persiste atómicamente `usuario`, `asignacion_rol` con rol `CLIENTE`, `cliente` vinculado y `evento_seguridad`, y responde HTTP `201 Created` con los datos del usuario sin exponer `password_hash`

#### Scenario: Reversión atómica cuando el documento ya pertenece a un cliente previo
- **WHEN** se envía `POST /auth/registro` con un `email` nuevo pero con un `documento` que ya existe en la tabla `cliente` (incluso si fue dado de alta en recepción sin usuario web)
- **THEN** el `UnitOfWork` revierte la transacción completa sin dejar filas huérfanas en `usuario` ni en `asignacion_rol`, no vincula la ficha existente y responde HTTP `409 Conflict` (`RN-02`)

#### Scenario: Conflicto por email ya registrado
- **WHEN** se envía `POST /auth/registro` con un `email` que ya pertenece a otro usuario registrado
- **THEN** el sistema rechaza la operación con HTTP `409 Conflict` sin modificar la base de datos

### Requirement: Autenticación por cookie HttpOnly y mitigación de ataques de tiempo (`POST /auth/login`)
El sistema MUST autenticar credenciales en `POST /auth/login` emitiendo el JWT exclusivamente en la cookie `access_token` (`HttpOnly`, `SameSite=Lax`), verificando contra `dummy_hash` si el correo no existe (`RN-09`), registrando cada intento en `intento_acceso` con sesión y `commit` propios, y devolviendo un mensaje genérico ante fallos.

#### Scenario: Inicio de sesión exitoso con emisión de cookie HttpOnly
- **WHEN** un usuario activo envía `POST /auth/login` con `email` y `password` válidos sin bloqueo por intentos fallidos
- **THEN** el sistema registra `IntentoAcceso(exito=True)` en una sesión independiente confirmada de inmediato, emite la cookie `access_token` (`HttpOnly`, `SameSite=Lax`) con un JWT `HS256` cuyos claims incluyen `sub`, `iat` flotante con microsegundos, `exp` y `roles` vigentes, y responde HTTP `200 OK` con `{"mensaje": "Sesión iniciada", "debe_cambiar_password": <bool>, "expira_en_segundos": <int>}` sin incluir el token en el cuerpo JSON

#### Scenario: Fallo de login por contraseña incorrecta con persistencia independiente del intento
- **WHEN** se envía `POST /auth/login` para un `email` existente con una `password` incorrecta (o usuario inactivo)
- **THEN** el sistema persiste `IntentoAcceso(exito=False)` en su propia sesión independiente con `commit` inmediato y responde HTTP `401 Unauthorized` con mensaje genérico `{"detail": "Credenciales inválidas."}`

#### Scenario: Mitigación de timing attack ante correo inexistente
- **WHEN** se envía `POST /auth/login` con un `email` que no existe en la tabla `usuario`
- **THEN** el sistema ejecuta `bcrypt.checkpw` en hilo separado contra el `dummy_hash` precalculado, persiste `IntentoAcceso(exito=False)` en sesión independiente y responde HTTP `401 Unauthorized` con el mismo mensaje genérico `{"detail": "Credenciales inválidas."}` (`RN-09`)

### Requirement: Limitación de intentos de acceso por ventana deslizante (`POST /auth/login`)
El sistema MUST rechazar con HTTP `429 Too Many Requests` y cabecera `Retry-After: 60` cualquier petición a `POST /auth/login` cuando existan 5 intentos fallidos consecutivos en los últimos 60 segundos para el mismo par `(email, ip)`, sin ejecutar `bcrypt`; un inicio de sesión exitoso MUST reiniciar el conteo sin borrar las filas históricas en `intento_acceso` (`RN-08`).

#### Scenario: Bloqueo en el sexto intento tras cinco fallos en 60 segundos
- **WHEN** se registran 5 intentos fallidos consecutivos para el mismo `email` e `ip` dentro de una ventana de 60 segundos y se envía un sexto intento
- **THEN** el sistema responde inmediatamente HTTP `429 Too Many Requests` con la cabecera `Retry-After: 60` sin invocar `bcrypt` y conservando los 5 fallos registrados en `intento_acceso` (`RN-08`)

#### Scenario: Reinicio de la cuenta tras un inicio de sesión exitoso
- **WHEN** un par `(email, ip)` acumula entre 1 y 4 intentos fallidos en los últimos 60 segundos, luego realiza un login exitoso (`exito=True`) y posteriormente vuelve a fallar una vez
- **THEN** el sistema contabiliza únicamente los fallos ocurridos después del último login exitoso sin borrar las filas previas de `intento_acceso`, permitiendo el intento sin responder `429`

### Requirement: Consulta de perfil autenticado y cierre de sesión (`GET /auth/yo`, `POST /auth/logout`)
El sistema MUST exponer `GET /auth/yo` en el grupo abierto de rutas devolviendo los datos del usuario autenticado (sin `password_hash`), sus roles vigentes consultados en tiempo real en base de datos (`roles`) y los roles declarados en el token JWT (`roles_token`), incluso si el usuario posee `debe_cambiar_password = True` (`RN-06`), y MUST exponer `POST /auth/logout` para eliminar la cookie `access_token` en el cliente.

#### Scenario: Consulta de perfil mostrando diferencia entre roles en base de datos y roles del token
- **WHEN** un usuario autenticado con cookie `access_token` válida consulta `GET /auth/yo` (incluso si tiene `debe_cambiar_password = True` o si sus roles fueron modificados después de emitir el JWT)
- **THEN** el sistema responde HTTP `200 OK` con `id`, `email`, `nombre`, `activo`, `debe_cambiar_password`, `roles` (roles vigentes actuales en `asignacion_rol`) y `roles_token` (claim `roles` del JWT)

#### Scenario: Rechazo de petición sin cookie aunque envíe Authorization Bearer
- **WHEN** un cliente invoca `GET /auth/yo` sin la cookie `access_token` pero enviando un token válido en la cabecera `Authorization: Bearer <jwt>`
- **THEN** el sistema ignora la cabecera `Authorization` y responde HTTP `401 Unauthorized`

#### Scenario: Cierre de sesión eliminando cookie
- **WHEN** un cliente invoca `POST /auth/logout`
- **THEN** el sistema responde HTTP `200 OK` incluyendo la instrucción `Set-Cookie` que expira la cookie `access_token` (`Max-Age=0`)

### Requirement: Cambio de contraseña e invalidación inmediata de sesiones por microsegundos (`POST /auth/cambiar-password`)
El sistema MUST permitir en `POST /auth/cambiar-password` (grupo abierto) verificar `password_actual`, actualizar `password_hash`, `debe_cambiar_password = False` y `password_cambiada_en` con microsegundos en UTC, registrar `EventoSeguridad` y emitir una nueva cookie `access_token` que invalide en el acto toda sesión anterior (`RN-06`, `RN-07`).

#### Scenario: Cambio de contraseña exitoso e invalidación instantánea de la cookie anterior
- **WHEN** un usuario autenticado envía `POST /auth/cambiar-password` con `password_actual` correcta y `password_nueva` válida inmediatamente después de haber iniciado sesión (sin espera entre ambas peticiones)
- **THEN** el sistema actualiza `password_hash`, establece `debe_cambiar_password = False` y `password_cambiada_en` en UTC con precisión de microsegundos, registra un `EventoSeguridad`, emite una nueva cookie `access_token` que funciona en peticiones subsiguientes (`200 OK`) y rechaza con HTTP `401 Unauthorized` cualquier petición posterior que utilice la cookie anterior (`iat < password_cambiada_en`) (`RN-07`)

#### Scenario: Rechazo de cambio de contraseña por clave actual incorrecta
- **WHEN** un usuario autenticado envía `POST /auth/cambiar-password` con una `password_actual` que no coincide con su `password_hash`
- **THEN** el sistema no modifica el usuario ni invalida la sesión actual y responde HTTP `401 Unauthorized`
