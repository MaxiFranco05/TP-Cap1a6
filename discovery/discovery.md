# Discovery — Taller Mecánico API

**Fecha**: 2026-10-23  
**Fuentes investigadas**: Consigna Oficial UTN Programación III (`TP_Cap1a6_Consigna.pdf`, 22 páginas)

---

## 1. Problema que resuelve

Un taller mecánico moderno necesita una API asincrónica y robusta para su operación diaria:
- La recepción da de alta a los clientes y sus vehículos, y genera órdenes de trabajo asociando fallas y repuestos requeridos.
- Los mecánicos toman las órdenes, realizan las reparaciones y las finalizan, descontando del stock cada repuesto utilizado.
- La administración gestiona el catálogo de repuestos, reposiciones de stock, personal y vigencia de roles con autoprotección.
- Los clientes disponen de autoservicio web para registrarse y consultar el estado de sus vehículos y órdenes sin intervención manual.

El sistema garantiza consistencia transaccional (Unit of Work), inmutabilidad de históricos mediante disparadores en base de datos y control de accesos estricto con cookies `HttpOnly`.

---

## 2. Usuarios / roles

- **ADMIN**: Administra personal y roles (con asignación, vigencia y autoprotección), mantiene el catálogo de repuestos, repone stock, consulta eventos de seguridad y puede terminar o cancelar órdenes de trabajo.
- **RECEPCION**: Da de alta clientes y vehículos, abre órdenes de trabajo para los vehículos ingresados, cancela órdenes y consulta repuestos.
- **MECANICO**: Visualiza órdenes asignables, inicia una orden pasando su estado a `EN_REPARACION` (quedando asignado a ella) y la finaliza (`TERMINADA`) registrando movimientos de stock e historial de forma atómica.
- **CLIENTE**: Se auto-registra en el sistema, consulta sus vehículos propios (`/mis-vehiculos`) y órdenes asociadas (`/mis-ordenes`), y puede cancelar órdenes en estado `PENDIENTE`.
- **SISTEMA**: Actor no-usuario registrado en el log de auditoría/seguridad para eventos iniciales (`seed.py`) y del sistema.

---

## 3. Casos de uso

1. **Auto-registro de cliente**: Como visitante, quiero registrar mi cuenta web para que se creen en una única transacción mi usuario, el rol `CLIENTE` y mi ficha de cliente sin conflictos ni datos huérfanos.
2. **Apertura de orden de trabajo**: Como personal de recepción, quiero abrir una orden de trabajo para un vehículo indicando la falla y los repuestos requeridos, naciendo en estado `PENDIENTE`.
3. **Ciclo de reparación mecánica**: Como mecánico, quiero iniciar una orden pendiente para asignármela e indicar que está en reparación, y luego marcarla como terminada para descontar automáticamente los repuestos del inventario.
4. **Gestión de inventario y precios**: Como administrador, quiero reponer stock de repuestos y ajustar precios registrando el motivo y asegurando que las tablas históricas mantengan una auditoría inmutable de sólo agregado.
5. **Autoprotección y vigencia de permisos**: Como administrador, quiero gestionar los roles del personal con fechas de expiración opcionales sin riesgo de que el sistema quede sin administradores activos ni que un administrador se auto-revoque.
6. **Autoservicio y cancelación**: Como cliente autenticado, quiero ver exclusivamente mis vehículos y órdenes, y cancelar una orden pendiente si decido no avanzar con la reparación.

---

## 4. Competidores / soluciones existentes

| Solución / Competidor | Problema que resuelve | Enfoque | Limitaciones / Diferenciadores |
|---|---|---|---|
| Sistemas de Gestión Tradicionales (GesTaller, TallerAlfa) | Gestión administrativa integral de talleres | Aplicaciones monolíticas de escritorio / ERPs cerrados | Complejidad alta, contratos acoplados y sin foco en API moderna asincrónica por capas. |
| Planillas de Cálculo / WhatsApp | Registro informal de clientes y órdenes | Manual | Inconsistencias, pérdida de trazabilidad, carreras de concurrencia y sin auditoría real. |
| **API Taller Mecánico (Esta solución)** | Backend de alto rendimiento para taller | API REST asincrónica (FastAPI + PostgreSQL + SQLModel) | Arquitectura por capas estricta (Router → Service → UoW → Repository → Model), transacciones ACID con UoW, triggers de sólo agregado en PostgreSQL y tokens en cookies `HttpOnly`. |

---

## 5. Funcionalidades necesarias (MVP - Capítulos 1 a 6)

- **Ciclo de vida y Health Checks**: Lifespan ASGI para inicialización limpia de motor/pool y sesión (`expire_on_commit=False`), cálculo de hash ficticio al inicio, cierre ordenado con `dispose()`, y endpoints `/health/live` (sin tocar DB) y `/health/ready` (`SELECT 1`).
- **Autenticación robusta**:
  - Hash de contraseñas con bcrypt fuera del event loop (`to_thread`) con semáforo y costo configurable.
  - Mitigación de timing attacks mediante verificación contra hash ficticio para correos inexistentes.
  - Rate limiting en login por IP/correo (5 fallos en 60s → 429 con `Retry-After`).
  - Límite de 72 bytes en contraseñas para evitar errores 500 no controlados.
  - Token JWT en cookie `HttpOnly` (`SameSite=Lax`, configurable `Secure`, sin token en cuerpo ni cabecera `Authorization`).
  - Flujo de cambio obligatorio de contraseña (`debe_cambiar_password`) con dos grupos de rutas (abierto vs protegido).
- **Autorización RBAC en base de datos**:
  - Verificación de roles activos y vigentes consultando PostgreSQL en cada petición protegida.
  - Distinción rigurosa entre 401 (sin autenticación o sesión inválida) y 403 (falta de permisos).
  - Autoprotección de administradores (impedir revocarse el rol propio y evitar dejar al sistema sin admins).
- **Contratos y CRUDs modulares**:
  - Módulos `health`, `usuarios`, `clientes`, `repuestos` y `ordenes`.
  - Contratos Pydantic estrictos con `extra="forbid"`, `exclude_unset` en PATCH y sin exponer `password_hash`.
  - Paginación estandarizada `{items, total, page, size, pages}` con control de límites (size 1..100, page válida o 422).
  - Borrado lógico en vehículos y repuestos con índices únicos parciales (`WHERE borrado_en IS NULL`).
- **Unit of Work y transacciones atómicas**:
  - UoW asincrónico para transacciones multirrecurso (auto-registro, finalización de órdenes, cambios de precio).
  - Repositorios genéricos (`BaseRepository[T]` y `SoftDeleteRepository[T]`) con llamadas exclusivas a `flush()` (nunca `commit()`).
  - Repositorio de catálogo sólo lectura para `estado_orden`.
- **Integridad y Disparadores en PostgreSQL**:
  - Disparador en base para impedir `UPDATE` o `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`.
  - Registro de intentos de acceso (`intento_acceso`) en sesión/transacción independiente para registrar fallos sin verse afectado por rollbacks.
- **Lecturas optimizadas y asincronía**:
  - Carga anticipada (eager loading) sin consultas N+1 en relaciones compuestas.
  - Aviso a clientes simulado con `BackgroundTasks` (`asyncio.sleep(0.5)`) que dispara solo tras commit exitoso.
- **Poblado inicial**:
  - Script `seed.py` para cargar estados obligatorios, usuarios de prueba, repuestos con stock inicial y órdenes de prueba.

---

## 6. Funcionalidades opcionales / Fuera de alcance

- **Control de concurrencia pesimista en stock** (Capítulo 7): Explícitamente fuera de alcance del TP. Se asume que dos finalizaciones simultáneas podrían generar una actualización perdida tolerada en esta entrega.
- **Colas de mensajes distribuidas con Redis/Celery** (Capítulo 8): El envío de avisos a clientes se resuelve en proceso con `BackgroundTasks`.
- **Frontend web interactivo**: La entrega se valida a través de la API REST y la suite de archivos `.http` y `.sql`.

---

## 7. Reglas de negocio (RN-01 a RN-20)

- **RN-01**: Unicidad de correo y documento en clientes; patente de vehículo y código de repuesto únicos entre los vigentes (`WHERE borrado_en IS NULL`).
- **RN-02**: Auto-registro atómico (crea usuario, rol `CLIENTE` y ficha de cliente; o las 3 filas o rollback completo; 409 si el documento ya pertenece a un cliente).
- **RN-03**: A lo sumo una asignación abierta por rol por usuario (`WHERE revocada_en IS NULL`).
- **RN-04**: Autorización resuelta consultando la base de datos en cada petición; roles en token sólo informativos.
- **RN-05**: Un administrador no puede revocarse su propio rol `ADMIN`; el sistema no puede quedar sin administradores vigentes.
- **RN-06**: Con cambio de clave pendiente, sólo se habilitan rutas `/auth` y de salud (`/health/*`).
- **RN-07**: Al cambiar clave, sesiones previas caducan inmediatamente comparando `iat` con `password_cambiada_en` (sin truncar a segundos).
- **RN-08**: Rate limiting: tras 5 fallos consecutivos para un correo e IP en 60s, respuesta 429 con cabecera `Retry-After`. Login exitoso reinicia el conteo.
- **RN-09**: Misma respuesta y mismo tiempo de procesamiento exista o no el correo (verificación contra hash ficticio).
- **RN-10**: Órdenes nacen `PENDIENTE` con al menos un ítem y sin repuestos repetidos; precios y totales calculados por el servidor.
- **RN-11**: Máquina de estados: `PENDIENTE` → `EN_REPARACION` → `TERMINADA` o `CANCELADA`.
- **RN-12**: Cancelación autorizada para recepción, administrador o dueño del vehículo; permisos evaluados antes que el estado (403 antes que 409).
- **RN-13**: Terminar una orden descuenta stock, crea movimientos y agrega historial en una única transacción atómica; si falta stock de algún ítem, rollback total.
- **RN-14**: Modificación de stock sólo permitida por movimientos (alta inicial, reposición y terminación de órdenes).
- **RN-15**: Tablas históricas de sólo agregado protegidas por disparador en PostgreSQL (prohibido `UPDATE` y `DELETE`).
- **RN-16**: Elementos dados de baja no se muestran ni se usan en nuevas órdenes; vehículos con órdenes abiertas no pueden darse de baja.
- **RN-17**: Rutas `/mis-*` exigen autenticación y restringen visibilidad a los recursos propios del cliente.
- **RN-18**: Ninguna excepción interna de base de datos se expone al cliente; traducción de `IntegrityError` y validaciones previas para evitar respuestas 500.
- **RN-19**: Catálogo de estados `estado_orden` inmutable desde la API; clave primaria código en texto legible.
- **RN-20**: Cada cambio de precio genera fila en `historial_precio_repuesto` en la misma transacción; un PATCH que no altera precio no inserta fila.

---

## 8. Integraciones

- **Motor de Base de Datos**: PostgreSQL 16 con controlador asincrónico `asyncpg` (o `psycopg3`).
- **Sin dependencias externas**: Sin consumo de servicios de terceros, APIs de mensajería externa ni colas auxiliares.

---

## 9. Restricciones técnicas

- **Lenguaje y Frameworks**: Python 3.12+, FastAPI >=0.111, SQLModel >=0.0.24, SQLAlchemy 2.0 asincrónico, Alembic >=1.13, pydantic-settings >=2.0, bcrypt >=4.0, PyJWT >=2.8.
- **Estructura modular obligatoria**: Router → Service → UoW → Repository → Model.
- **Migraciones**: Esquema creado exclusivamente con Alembic (2 migraciones: 1 con `autogenerate` para tablas e índices, 1 manual para disparadores de sólo agregado).
- **Tipos estrictos**: Moneda en `NUMERIC(10,2)` / `NUMERIC(12,2)` y `Decimal` en Python; fechas con `timestamptz`.
- **Secretos**: Sin claves en código fuente ni en git; lectura desde variables de entorno con `pydantic-settings`.

---

## 10. Riesgos

- **Concurrencia en stock**: Posible condición de carrera en alta concurrencia aceptada en el alcance del proyecto.
- **BackgroundTasks volátil**: Pérdida de aviso simulado si el proceso cae antes de enviar el callback (tolerable por ser simulación educativa).
- **Comparación de tiempos en JWT**: Errores si se redondea `iat` a segundos enteros durante el flujo de cambio de clave.
- **Límite de 72 bytes en bcrypt**: Riesgo de error 500 si el contrato Pydantic no valida la longitud máxima en bytes de contraseñas.

---

## 11. Preguntas abiertas

- Definir si se incluye un archivo `docker-compose.yml` para levantar la base de datos PostgreSQL 16 localmente y agilizar las pruebas.
