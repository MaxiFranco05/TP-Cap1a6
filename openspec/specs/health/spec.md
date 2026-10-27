# health Specification

## Purpose
Proveer endpoints de sondeo de salud operativa (liveness y readiness) para verificar la disponibilidad del proceso web FastAPI y la conectividad activa hacia la base de datos PostgreSQL.

## Requirements

### Requirement: Liveness Probe
El sistema SHALL exponer un endpoint `GET /health/live` que confirme la disponibilidad del proceso de la aplicación sin realizar consultas a la base de datos.

#### Scenario: Proceso web en ejecucion
- **WHEN** un cliente realiza una petición `GET /health/live`
- **THEN** el sistema responde inmediatamente con código HTTP 200 y el cuerpo `{"status": "live"}`

### Requirement: Readiness Probe
El sistema SHALL exponer un endpoint `GET /health/ready` que valide la conectividad activa con PostgreSQL ejecutando una consulta `SELECT 1`.

#### Scenario: Base de datos disponible
- **WHEN** un cliente realiza una petición `GET /health/ready` y la conexión con PostgreSQL responde correctamente
- **THEN** el sistema responde con código HTTP 200 y el cuerpo `{"status": "ready"}`

#### Scenario: Base de datos no disponible
- **WHEN** un cliente realiza una petición `GET /health/ready` y la conexión con PostgreSQL falla, es rechazada o entra en timeout
- **THEN** el sistema responde con código HTTP 503 Service Unavailable y el cuerpo `{"status": "database unavailable"}`
