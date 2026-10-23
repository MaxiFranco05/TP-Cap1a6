# Descripción General

## Stack tecnológico

| Componente | Versión mínima | Uso en el proyecto |
|---|---|---|
| **Python** | 3.12 | Lenguaje de desarrollo backend. |
| **FastAPI** | 0.111 | Framework web asincrónico; todos los handlers declarados con `async def`. |
| **SQLModel** | 0.0.24 | Definición de modelos de base de datos combinando SQLAlchemy y Pydantic. |
| **SQLAlchemy** | 2.0 (asincrónico) | Motor relacional, sesión asincrónica (`AsyncSession`) y carga anticipada (`selectinload`). |
| **asyncpg** | 0.30 | Driver/controlador asincrónico para PostgreSQL (`postgresql+asyncpg://`). |
| **PostgreSQL** | 16 | Servidor de base de datos relacional con soporte transaccional y disparadores PL/pgSQL. |
| **Alembic** | 1.13 | Control de versiones y migraciones de base de datos con plantilla asincrónica. |
| **pydantic-settings** | 2.0 | Gestión tipada de variables de entorno mediante clase `Settings`. |
| **bcrypt** | 4.0 | Hashing seguro de contraseñas (costo configurable, fuera del bucle de eventos). |
| **PyJWT** | 2.8 | Emisión y verificación de tokens de autenticación firmados criptográficamente. |
| **uvicorn** | fastapi[standard] | Servidor ASGI para ejecución de la aplicación web asincrónica. |

---

## Arquitectura general

La aplicación adopta una arquitectura modular en **6 capas estrictas** por módulo funcional:

```
Petición HTTP (Cookie HttpOnly)
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ 1. ROUTER (app/modules/<modulo>/router.py)             │
│    - Define rutas FastAPI y dependencias (Auth / UoW)   │
│    - Recibe DTOs de entrada y valida contratos         │
│    - Pasa UoW al servicio; traduce excepciones dominio  │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 2. SERVICE (app/modules/<modulo>/service.py)           │
│    - Orquesta las reglas de negocio (RN-01 a RN-20)     │
│    - Abre el Unit of Work con `async with uow:`         │
│    - Ejecuta validaciones previas y cálculos           │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 3. UNIT OF WORK (app/modules/<modulo>/unit_of_work.py) │
│    - Controla el ciclo de la transacción (ACID)        │
│    - Expone repositorios asociados a la misma sesión   │
│    - Ejecuta `commit()` o `rollback()` al salir         │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 4. REPOSITORY (app/modules/<modulo>/repository.py)     │
│    - Abstrae consultas SQL / SQLAlchemy               │
│    - Declara precarga de relaciones (`selectinload`)   │
│    - Usa exclusivamente `flush()`, nunca `commit()`    │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 5. MODEL (app/modules/<modulo>/models.py)              │
│    - Clases SQLModel mapeadas a tablas PostgreSQL      │
│    - Restricciones CHECK, índices parciales y FKs      │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 6. DATABASE (PostgreSQL 16 Engine & Session)           │
│    - Disparadores de sólo agregado en PL/pgSQL         │
│    - Restricciones de integridad referencial           │
└────────────────────────────────────────────────────────┘
```

### Reglas arquitectónicas de oro:
1. **Separación de responsabilidades**: Cada capa conoce solo la inmediata inferior. El router no hace consultas directas; el servicio no gestiona HTTP; el repositorio nunca confirma (`commit()`).
2. **Ciclo de vida y sesiones**: El motor y la fábrica de sesiones se instancian en el `lifespan` ASGI (`app.state`) y no al importar módulos, evitando incompatibilidades con el bucle de eventos (`asyncio`).
3. **Manejo de transacciones**: Las operaciones multiescritura (ej. auto-registro o finalización de órdenes) viven en un único bloque transaccional del Unit of Work.
4. **Cero texto interno de DB**: Los errores de base de datos (`IntegrityError`) se interceptan y traducen a respuestas de dominio (409/422), impidiendo filtraciones del esquema interno.

---

## Integraciones externas

| Componente | Tipo | Propósito | Protocolo / Interfaz |
|---|---|---|---|
| **PostgreSQL 16** | Base de datos relacional | Persistencia de datos, triggers y consistencia ACID. | `postgresql+asyncpg` / TCP 5432 |
| **Cliente HTTP / Navegador** | Consumidor de API | Consumo de servicios REST con cookies seguras. | HTTP/1.1 o HTTP/2 (JSON) |

*Nota*: No existen integraciones con pasarelas de pago ni APIs de mensajería externas en este alcance.

---

## Estructura de Rutas y Endpoints de Referencia

La API se divide en dos grupos de rutas configurados en `main.py`:
1. **Grupo Abierto**: Rutas públicas y de autenticación previa.
2. **Grupo Protegido**: Rutas que aplican middleware de control para usuarios autenticados sin cambio de contraseña pendiente. Si un usuario tiene contraseña pendiente, este grupo responde **403**.

### Matriz de Endpoints

| Grupo | Método | Ruta | Acceso requerido | Códigos HTTP esperados |
|---|---|---|---|---|
| **Abierto** | GET | `/health/live` | Cualquiera | 200 |
| **Abierto** | GET | `/health/ready` | Cualquiera | 200, 503 |
| **Abierto** | POST | `/auth/registro` | Cualquiera | 201, 409, 422 |
| **Abierto** | POST | `/auth/login` | Cualquiera | 200, 401, 422, 429 |
| **Abierto** | POST | `/auth/logout` | Cualquiera | 200 |
| **Abierto** | GET | `/auth/yo` | Autenticado | 200, 401 |
| **Abierto** | POST | `/auth/cambiar-password` | Autenticado | 200, 401, 422 |
| **Protegido** | POST | `/usuarios` | ADMIN | 201, 409, 422 |
| **Protegido** | GET | `/usuarios/{id}/roles` | ADMIN | 200, 404 |
| **Protegido** | POST | `/usuarios/{id}/roles` | ADMIN | 201, 404, 409, 422 |
| **Protegido** | DELETE | `/usuarios/{id}/roles/{rol}` | ADMIN | 200, 404, 409 |
| **Protegido** | GET | `/eventos` | ADMIN | 200, 422 |
| **Protegido** | POST | `/clientes` | RECEPCION, ADMIN | 201, 409, 422 |
| **Protegido** | GET | `/clientes/{id}` | RECEPCION, ADMIN | 200, 404 |
| **Protegido** | POST | `/clientes/{id}/vehiculos` | RECEPCION, ADMIN | 201, 404, 409, 422 |
| **Protegido** | DELETE | `/vehiculos/{id}` | RECEPCION, ADMIN | 204, 404, 409 |
| **Protegido** | GET | `/mis-vehiculos` | Autenticado (CLIENTE) | 200 |
| **Protegido** | GET | `/repuestos` | ADMIN, RECEPCION, MECANICO | 200, 422 |
| **Protegido** | GET | `/repuestos/{id}` | ADMIN, RECEPCION, MECANICO | 200, 404 |
| **Protegido** | POST | `/repuestos` | ADMIN | 201, 409, 422 |
| **Protegido** | PATCH | `/repuestos/{id}` | ADMIN | 200, 404, 422 |
| **Protegido** | DELETE | `/repuestos/{id}` | ADMIN | 204, 404 |
| **Protegido** | POST | `/repuestos/{id}/reponer` | ADMIN | 200, 404, 422 |
| **Protegido** | GET | `/repuestos/{id}/movimientos` | ADMIN | 200, 404 |
| **Protegido** | GET | `/repuestos/{id}/precios` | ADMIN | 200, 404 |
| **Protegido** | POST | `/ordenes` | RECEPCION, ADMIN | 201, 409, 422 |
| **Protegido** | GET | `/ordenes` | ADMIN, RECEPCION, MECANICO | 200, 422 |
| **Protegido** | GET | `/ordenes/{id}` | Personal o Dueño del Vehículo | 200, 403, 404 |
| **Protegido** | POST | `/ordenes/{id}/iniciar` | MECANICO | 200, 404, 409 |
| **Protegido** | POST | `/ordenes/{id}/terminar` | Mecánico asignado o ADMIN | 200, 403, 404, 409 |
| **Protegido** | POST | `/ordenes/{id}/cancelar` | RECEPCION, ADMIN o Dueño | 200, 403, 404, 409 |
| **Protegido** | GET | `/estados-orden` | Autenticado | 200 |
| **Protegido** | GET | `/mis-ordenes` | Autenticado (CLIENTE) | 200, 422 |
