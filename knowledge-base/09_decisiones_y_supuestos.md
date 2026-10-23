# Decisiones y Supuestos

Este documento compila las decisiones de arquitectura y diseño clave (DD) tomadas a partir de la consigna oficial, junto con los supuestos inferidos (SU).

---

## Decisiones Documentadas

### DD-01 — Arquitectura en Capas y Unit of Work Asincrónico
- **Decisión**: Estructurar cada módulo en 6 capas (Router → Service → UoW → Repository → Model → Database), donde el Unit of Work controla el ciclo transaccional (`commit()` / `rollback()`) y los repositorios solo ejecutan `flush()`.
- **Contexto**: Las operaciones del dominio (auto-registro, terminar orden, actualizar precio) afectan múltiples tablas y exigen garantías ACID estrictas.
- **Alternativas consideradas**: Control transaccional directo en servicios o handlers con `session.commit()`.
- **Justificación**: Centraliza la responsabilidad transaccional en un gestor de contexto asincrónico, asegurando que un fallo en cualquier escritura revierta todo el bloque de manera atómica sin dejar datos huérfanos.
- **Trade-offs aceptados**: Mayor cantidad de capas y código boilerplate de repositorios/UoW, ampliamente compensado por la robustez y testeabilidad.

---

### DD-02 — Autenticación Exclusiva por Cookies `HttpOnly`
- **Decisión**: Transportar el JWT de autenticación exclusivamente mediante una cookie `access_token` con directivas `HttpOnly`, `SameSite=Lax` y `Max-Age`. No exponer el token en el cuerpo JSON ni aceptar `Authorization: Bearer` en peticiones protegidas.
- **Contexto**: Blindar la aplicación contra ataques de filtración de credenciales por Cross-Site Scripting (XSS).
- **Alternativas consideradas**: Token Bearer en headers HTTP almacenado en `localStorage`.
- **Justificación**: Una cookie `HttpOnly` no puede ser leída por scripts maliciosos de JavaScript en el navegador.
- **Trade-offs aceptados**: Exige configurar atributos como `SameSite` y manejar clientes REST mediante cookies manuales o cabecera `Cookie`.

---

### DD-03 — Autorización RBAC Dinámica en Base de Datos
- **Decisión**: La dependencia `requiere_rol` consulta la tabla `asignacion_rol` en la base de datos en cada petición protegida para validar si el rol está vigente (`vence_en IS NULL OR vence_en > NOW()` y `revocada_en IS NULL`). Los roles dentro del JWT son meramente informativos.
- **Contexto**: Al revocar un rol a un usuario, el impacto debe ser instantáneo sin esperar a que el token expire.
- **Alternativas consideradas**: Autorizar basándose exclusivamente en los claims embebidos en el JWT.
- **Justificación**: Cumple con la regla de negocio RN-04 y garantiza que la revocación de privilegios surta efecto en la siguiente petición.
- **Trade-offs aceptados**: Añade una consulta SQL liviana por cada petición protegida.

---

### DD-04 — Esquema Versionado con Alembic y Migración Manual de Triggers
- **Decisión**: Prohibir `create_all` y entregar exactamente dos migraciones: la primera autogenerada para el esquema inicial, y la segunda escrita a mano para instalar los disparadores de sólo agregado (`RN-15`).
- **Contexto**: Alembic autogenerate no detecta funciones almacenadas ni triggers de base de datos.
- **Alternativas consideradas**: Script SQL separado ejecutado al margen de las migraciones.
- **Justificación**: Garantiza que `alembic upgrade head` sobre una base vacía cree el 100% del esquema con sus reglas de integridad de forma reproducible.

---

### DD-05 — Catálogo `estado_orden` con Clave Primaria Textual
- **Decisión**: Modelar los estados de las órdenes en una tabla catálogo `estado_orden` donde la clave primaria es el código (`PENDIENTE`, `EN_REPARACION`, etc.) y no un entero subrogado (`id`).
- **Contexto**: La columna `orden_trabajo.estado` debe leerse de forma idéntica e intuitiva tanto en `psql` como en los contratos de la API.
- **Alternativas consideradas**: Enum nativo de PostgreSQL o campo entero con clave foránea a un id.
- **Justificación**: Permite que el catálogo almacene metadatos (como `posicion` y `es_final`) manteniendo legibilidad directa y consistencia con los enums de Python.

---

### DD-06 — Borrado Lógico con Índices Únicos Parciales
- **Decisión**: Implementar soft delete en `vehiculo` y `repuesto` mediante `borrado_en: datetime | None`, asegurando unicidad mediante índices parciales: `CREATE UNIQUE INDEX ... WHERE borrado_en IS NULL`.
- **Contexto**: Un auto vendido dado de baja o un repuesto discontinuado no deben impedir que un nuevo propietario registre la misma patente.
- **Alternativas consideradas**: Borrado físico con cascada, o índices únicos simples.
- **Justificación**: Preserva la integridad referencial histórica de órdenes viejas y habilita la reutilización de identificadores comerciales.

---

### DD-07 — Mitigación de Timing Attacks y Rate Limiting
- **Decisión**: Validar contra un hash ficticio de bcrypt si el correo no existe, y contar intentos fallidos en `intento_acceso` bloqueando con 429 tras 5 fallos en 60s.
- **Contexto**: Evitar ataques de enumeración de usuarios basados en diferencias de tiempo de respuesta (timing attacks) y ataques de fuerza bruta de contraseñas.
- **Alternativas consideradas**: Retorno inmediato de error 404/401 sin verificar bcrypt.
- **Justificación**: Oculta la existencia de cuentas y protege contra ataques automatizados de diccionario.

---

### DD-08 — Creación de Motor y Sesión en Lifespan ASGI
- **Decisión**: Instanciar el motor SQLAlchemy y la fábrica de sesiones dentro del manejador `lifespan` de FastAPI, guardándolos en `app.state`, cerrando con `dispose()` al apagar.
- **Contexto**: Evitar el antipatrón EA-08 donde recursos asincrónicos se crean al importar módulos antes de que exista el event loop.
- **Alternativas consideradas**: Variables globales a nivel de módulo `db = create_async_engine(...)`.
- **Justificación**: Elimina fallas silenciosas en suites de pruebas y garantiza compatibilidad total con el ciclo de vida de ASGI.

---

## Supuestos Inferidos

### SU-01 — Base de Datos PostgreSQL 16 Disponible
- **Supuesto**: Se dispone de un servidor PostgreSQL 16 accesible localmente o mediante contenedor Docker en el puerto 5432.
- **Origen**: Requisitos técnicos obligatorios de la consigna.
- **Riesgo si es falso**: La suite de pruebas no puede conectarse ni ejecutar las migraciones.
- **Validación**: Comprobación con `GET /health/ready` y conexión inicial con `asyncpg`.

---

### SU-02 — Precisión de Microsegundos en Tokens JWT
- **Supuesto**: La librería `PyJWT` y el campo `iat` soportan marcas de tiempo de punto flotante o microsegundos, lo cual se compara directamente contra `password_cambiada_en` sin redondear a segundos enteros.
- **Origen**: Nota técnica explícita en página 13 ("El iat no se trunca a segundos").
- **Riesgo si es falso**: Una sesión creada inmediatamente tras el cambio de clave podría ser invalidada por coincidencia de segundo.
- **Validación**: Pruebas unitarias de emisión y validación de tokens en el mismo instante del cambio de clave.

---

### SU-03 — Concurrencia de Stock Tolerada
- **Supuesto**: Se asume que no se implementará bloqueo pesimista (`SELECT FOR UPDATE`) para stock en este entregable (Capítulo 7), por lo que la cátedra no penalizará condiciones de carrera bajo solicitudes paralelas extremas.
- **Origen**: Sección "Qué queda afuera" (página 2).
- **Riesgo si es falso**: Ninguno, está explícitamente documentado como fuera de alcance.

---

### SU-04 — Simulación en Memoria de Avisos al Cliente
- **Supuesto**: El aviso al cliente al terminar una orden se simula con `await asyncio.sleep(0.5)` y un mensaje en el log vía `BackgroundTasks`. Si el proceso se reinicia, la pérdida de la tarea es aceptable.
- **Origen**: Sección "Qué queda afuera" y Ejercicio 8.
- **Riesgo si es falso**: Ninguno, está formalmente avalado en las consignas de la materia.
