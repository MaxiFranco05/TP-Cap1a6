# Preguntas Abiertas

## Inconsistencias Detectadas y Resolución

### IN-01 — Controlador Asincrónico de PostgreSQL (`asyncpg` vs `psycopg3`)
- **Consigna dice**: La tabla de requisitos menciona `asyncpg 0.30` como versión mínima, pero aclara que también se acepta `psycopg 3 asincrónico`.
- **Impacto**: La URL de conexión difiere ligeramente (`postgresql+asyncpg://` vs `postgresql+psycopg://`).
- **Resolución adoptada**: Se adopta `asyncpg` como estándar primario por su alto rendimiento y adopción nativa en FastAPI y SQLAlchemy 2.0 asincrónico, permitiendo configuración flexible en `DATABASE_URL`.

### IN-02 — Simulación de Tarea en Segundo Plano vs Notificación Real
- **Consigna dice**: En la sección de requerimientos se pide simular el aviso con `await asyncio.sleep(0.5)` y un mensaje en el log.
- **Impacto**: No se requiere integrar ningún proveedor de email o SMS (Sendgrid, Twilio, etc.).
- **Resolución adoptada**: Mantener la simulación mediante `BackgroundTasks` de FastAPI tal cual especifica la consigna, garantizando que el log solo se emita si la transacción de base de datos confirmó exitosamente.

---

## Preguntas Abiertas Priorizadas

| Prioridad | Pregunta / Decisión | Bloquea | Decisor Recomendado | Resolución Propuesta |
|:---:|---|---|---|---|
| **Media** | ¿Se provee un archivo `docker-compose.yml` para instanciar PostgreSQL 16 localmente? | Setup y pruebas | Desarrollador / Alumno | Proveer un `docker-compose.yml` opcional para levantar PostgreSQL 16 en puerto 5432 sin contaminar el sistema operativo anfitrión. |
| **Media** | ¿Se agregan tests automáticos con `pytest` y `httpx.AsyncClient` además de los archivos `.http`? | Verificación TDD | Equipo técnico | Sí, implementar una suite con `pytest-asyncio` que automatice la ejecución de los 19 casos de prueba mínimos (C-01 a C-19) de forma reproducible. |
| **Baja** | ¿El script `seed.py` debe ser idempotente (limpiar antes de insertar)? | Ejecución de pruebas | Cátedra / Alumno | Sí, `seed.py` ejecuta limpieza (TRUNCATE o DELETE CASCADE) antes de poblar los estados, usuarios, repuestos y órdenes canónicas. |

---

## Confirmación de Campos de Discovery Arquitectónico (`state.kb.discovery`)

Los siguientes 6 campos fueron consolidados a partir de la consigna oficial:
- **`problem`**: "Un taller mecánico necesita una API asincrónica y robusta para su trabajo diario: clientes, vehículos, órdenes de trabajo, stock de repuestos, gestión de roles de personal y autoservicio web de clientes, garantizando consistencia transaccional y reglas de negocio estrictas."
- **`system_type`**: `api` (API REST asincrónica por capas)
- **`domain`**: `taller_mecanico` (Automotriz, reparaciones e inventario)
- **`scale`**: `team` (Uso operativo de taller con autoservicio web para clientes)
- **`stack`**: `["Python 3.12", "FastAPI", "SQLModel", "SQLAlchemy 2.0 asincrónico", "asyncpg", "PostgreSQL 16", "Alembic", "pydantic-settings", "bcrypt", "PyJWT", "uvicorn"]`
- **`needs_infra`**: `true` (Requiere servidor de base de datos relacional PostgreSQL 16)
