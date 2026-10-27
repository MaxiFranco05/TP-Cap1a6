# app-lifecycle Specification

## Purpose
Gestionar la configuración fuertemente tipada del sistema leída desde el entorno, el ciclo de vida asincrónico ASGI con recursos en app.state, y el envoltorio estándar de paginación.

## Requirements

### Requirement: Tipado y validacion de configuracion
El sistema SHALL leer su configuración desde variables de entorno mediante `pydantic-settings` sin permitir valores por defecto para secretos críticos y componiendo la URL de base de datos asincrónica.

#### Scenario: Inicio con variables completas
- **WHEN** la aplicación arranca con todas las variables requeridas en `.env` o variables de entorno del sistema
- **THEN** la configuración se carga exitosamente y expone la propiedad `DATABASE_URL` con esquema asincrónico `postgresql+asyncpg://`

#### Scenario: Inicio sin secretos criticos
- **WHEN** la aplicación arranca sin definir `POSTGRES_PASSWORD` o `JWT_SECRET_KEY`
- **THEN** el arranque de la aplicación falla inmediatamente con error de validación impidiendo operar con credenciales inseguras

### Requirement: Gestion de ciclo de vida ASGI en app.state
El sistema SHALL inicializar el motor asincrónico y la fábrica de sesiones dentro del manejador `lifespan` de FastAPI, almacenándolos en `app.state`, y cerrando el motor con `dispose()` al apagar.

#### Scenario: Arranque del servidor
- **WHEN** el servidor ASGI inicia su ciclo de vida
- **THEN** se crea el motor asincrónico en `app.state.engine`, se precalcula el hash ficticio de bcrypt y la fábrica de sesiones asincrónicas se configura con `expire_on_commit=False`

#### Scenario: Apagado del servidor
- **WHEN** el servidor ASGI finaliza su ejecución
- **THEN** se ejecuta la limpieza asincrónica invocando `dispose()` sobre el motor y liberando todas las conexiones del pool

### Requirement: Envoltorio estandar de paginacion
El sistema SHALL proveer un DTO genérico de paginación con el formato `{items, total, page, size, pages}` que valide límites de tamaño y cálculo de páginas.

#### Scenario: Parametros de paginacion validos
- **WHEN** se solicitan datos paginados con `page >= 1` y `size` entre 1 y 100
- **THEN** el sistema calcula `pages = ceil(total / size)` (o 1 si total es 0) y devuelve el envoltorio estructurado

#### Scenario: Tamaño de pagina fuera de rango
- **WHEN** se recibe un parámetro de consulta `size` menor a 1 o mayor a 100
- **THEN** el sistema rechaza la petición con código HTTP 422 Unprocessable Entity
