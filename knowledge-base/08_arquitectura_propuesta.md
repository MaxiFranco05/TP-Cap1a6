# Arquitectura Propuesta

## Patrones de Diseño Aplicados

| Patrón | Dónde se aplica | Propósito y Justificación |
|---|---|---|
| **Arquitectura en Capas** | Todo el backend (Router → Service → UoW → Repository → Model) | Separación estricta de responsabilidades: cada capa sabe lo suyo y nada más. Facilita testeabilidad y mantenimiento. |
| **Unit of Work (UoW)** | `app/core/unit_of_work.py` y `app/modules/<modulo>/unit_of_work.py` | Gestor de contexto asincrónico que agrupa múltiples operaciones en una única transacción de base de datos; asegura atomicidad (ACID) y controla `commit()` / `rollback()`. |
| **Repository Pattern** | `app/core/repository.py` (`BaseRepository[T]`, `SoftDeleteRepository[T]`) | Abstrae la persistencia y consultas a la base de datos. Solo ejecuta `flush()`, nunca `commit()`. |
| **Read-Only Repository** | Catálogo `estado_orden` en módulo `ordenes` | Repositorio que solo ofrece métodos de lectura, sin exponer `add/update/delete`. |
| **Eager Loading (Precarga)** | Métodos de repositorios que consultan relaciones | Uso explícito de `selectinload` para resolver relaciones compuestas en un número constante de consultas, eliminando problemas de consultas N+1. |
| **Append-Only (Sólo Agregado)** | Tablas `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto` | Disparadores PL/pgSQL en base de datos que abortan `UPDATE` y `DELETE` para garantizar inmutabilidad absoluta de auditoría. |
| **Timing Attack Mitigation** | Servicio de autenticación (`app/modules/usuarios/service.py`) | Verificación contra hash ficticio precalculado cuando el usuario no existe, igualando los tiempos de respuesta. |
| **Independent Session Audit** | Registro de `intento_acceso` en login | Uso de sesión y transacción independientes que hacen commit inmediato para que los registros de intentos fallidos sobrevivan a rollbacks. |

---

## Estructura Obligatoria de Directorios

La estructura de archivos es obligatoria y responde exactamente a los requerimientos de la cátedra:

```
TP_Cap1a6/
├── main.py                             # Aplicación FastAPI, lifespan ASGI y montaje de los dos grupos de rutas
├── seed.py                             # Poblado inicial del catálogo y datos canónicos de prueba
├── requirements.txt                    # Dependencias congeladas del proyecto
├── alembic.ini                         # Configuración de Alembic para migraciones
├── env.example                         # Plantilla de variables de entorno sin secretos
├── .env                                # Variables locales de entorno (NO se versiona en git)
│
├── app/
│   ├── core/
│   │   ├── config.py                   # Settings con pydantic-settings y @computed_field para database_url
│   │   ├── database.py                 # Creación del motor asincrónico, fábrica de sesiones y get_session
│   │   ├── security.py                 # Bcrypt fuera del event loop, emisión y verificación de JWT
│   │   ├── dependencies.py             # Inyección: usuario actual, roles vigentes en DB, requiere_rol
│   │   ├── repository.py               # BaseRepository[T] y SoftDeleteRepository[T]
│   │   ├── paginacion.py               # Envoltorio {items, total, page, size, pages} y cálculo de páginas
│   │   └── unit_of_work.py             # UnitOfWork base abstracto como gestor de contexto asincrónico
│   │
│   └── modules/
│       ├── health/
│       │   └── router.py               # Endpoints /health/live y /health/ready
│       │
│       ├── usuarios/
│       │   ├── models.py               # Usuario, AsignacionRol, IntentoAcceso, EventoSeguridad
│       │   ├── schemas.py              # DTOs de login, registro, personal, roles
│       │   ├── repository.py           # UsuarioRepository, AsignacionRolRepository, etc.
│       │   ├── unit_of_work.py         # UsuariosUnitOfWork
│       │   ├── service.py              # Lógica de login, rate limit, tokens, roles
│       │   └── router.py               # Rutas /auth/*, /usuarios/*, /eventos
│       │
│       ├── clientes/
│       │   ├── models.py               # Cliente, Vehiculo (con borrado lógico e índice parcial)
│       │   ├── schemas.py              # DTOs de clientes y vehículos
│       │   ├── repository.py           # ClienteRepository, VehiculoRepository
│       │   ├── unit_of_work.py         # ClientesUnitOfWork
│       │   ├── service.py              # Lógica de clientes y vehículos, validación de órdenes abiertas
│       │   └── router.py               # Rutas /clientes/*, /vehiculos/*, /mis-vehiculos
│       │
│       ├── repuestos/
│       │   ├── models.py               # Repuesto, MovimientoStock, HistorialPrecioRepuesto
│       │   ├── schemas.py              # DTOs de repuestos, reposición, actualización (sin stock)
│       │   ├── repository.py           # RepuestoRepository, MovimientoStockRepository, etc.
│       │   ├── unit_of_work.py         # RepuestosUnitOfWork
│       │   ├── service.py              # Lógica de stock, reposición, actualización de precios
│       │   └── router.py               # Rutas /repuestos/*
│       │
│       └── ordenes/
│           ├── models.py               # EstadoOrden (catálogo), OrdenTrabajo, ItemOrden, HistorialEstadoOrden
│           ├── schemas.py              # DTOs de órdenes e ítems
│           ├── repository.py           # EstadoOrdenRepository (read-only), OrdenTrabajoRepository
│           ├── unit_of_work.py         # OrdenesUnitOfWork
│           ├── service.py              # Transiciones PENDIENTE -> EN_REPARACION -> TERMINADA / CANCELADA
│           └── router.py               # Rutas /ordenes/*, /estados-orden, /mis-ordenes
│
├── migrations/
│   ├── env.py                          # Configuración asincrónica de migraciones Alembic
│   ├── script.py.mako                  # Plantilla mako
│   └── versions/
│       ├── 001_initial_schema.py       # Migración autogenerada con tablas e índices
│       └── 002_append_only_triggers.py # Migración manual con triggers de sólo agregado (RN-15)
│
└── test/
    ├── *.http                          # Casos de prueba interactivos C-01 a C-19
    └── solo_agregado.sql               # Script psql con los 6 rechazos de disparadores para C-14
```

---

## Seguridad

1. **Gestión de Contraseñas**:
   - `bcrypt` ejecutado en hilo secundario (`asyncio.to_thread`) dentro de un semáforo (`asyncio.Semaphore(value=settings.BCRYPT_MAX_CONCURRENCY)`).
   - Costo (rounds) definido en configuración (`settings.BCRYPT_ROUNDS`), no fijo en el código.
   - Restricción estricta de 72 bytes en contratos Pydantic para contraseñas de entrada.
2. **Tokens y Cookies**:
   - JWT firmado exclusivamente con algoritmo HMAC-SHA256 (`HS256`).
   - Secret key leída de variable de entorno sin valor por defecto.
   - El token viaja únicamente en cookie `HttpOnly`, `SameSite=Lax`, `Max-Age` acorde a expiración y `Secure` según ambiente.
3. **Control de Intentos de Acceso**:
   - Tabla `intento_acceso` con índice compuesto `(email, ip, cuando)`.
   - Consulta previa al intento de verificación de contraseña; si `count >= 5` en 60s, corta inmediatamente con 429.
4. **Validación Exhaustiva de Contratos**:
   - Todos los esquemas Pydantic configurados con `model_config = ConfigDict(extra="forbid")`.

---

## Configuración y Variables de Entorno

```python
class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_SECONDS: int = 1800  # 30 minutos
    
    COOKIE_SECURE: bool = False
    BCRYPT_ROUNDS: int = 12
    BCRYPT_MAX_CONCURRENCY: int = 4
    DB_POOL_SIZE: int = 10
    SQL_ECHO: bool = False

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
```

### Tabla de Variables de Entorno (`env.example`)

| Variable | Descripción | Ejemplo | ¿Sensible? |
|---|---|---|:---:|
| `POSTGRES_USER` | Usuario de PostgreSQL | `taller_user` | No |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL | `secret_password` | **SÍ** |
| `POSTGRES_DB` | Nombre de la base de datos | `taller_db` | No |
| `POSTGRES_HOST` | Host del servidor de base de datos | `localhost` | No |
| `POSTGRES_PORT` | Puerto de conexión a PostgreSQL | `5432` | No |
| `JWT_SECRET_KEY` | Clave secreta para firma de JWT | `openssl rand -hex 32` | **SÍ** |
| `JWT_ALGORITHM` | Algoritmo criptográfico para JWT | `HS256` | No |
| `JWT_EXPIRATION_SECONDS` | Duración de la cookie de sesión | `1800` | No |
| `COOKIE_SECURE` | Flag Secure para cookies (True en prod) | `false` | No |
| `BCRYPT_ROUNDS` | Factor de trabajo de bcrypt | `12` | No |
| `BCRYPT_MAX_CONCURRENCY` | Límite concurrente de hashes bcrypt | `4` | No |
| `DB_POOL_SIZE` | Tamaño del pool de conexiones async | `10` | No |
| `SQL_ECHO` | Muestra consultas SQL en consola | `true` | No |
