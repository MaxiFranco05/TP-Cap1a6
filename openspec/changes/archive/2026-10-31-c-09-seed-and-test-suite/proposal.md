# Proposal: c-09-seed-and-test-suite

## Why

El sistema de gestión del taller mecánico requiere un mecanismo oficial, determinístico y reproducible para inicializar la base de datos con los datos canónicos (`seed.py`) y una batería de verificación integral (`test/` con archivos `.http`, `solo_agregado.sql` y `README.md`) para validar de forma interactiva y automatizada los 19 casos de prueba oficiales de la cátedra (C-01 a C-19), completando el alcance requerido para los Capítulos 1 a 6.

## What Changes

- **Script de carga inicial canónico e idempotente (`seed.py`)**:
  - Script independiente ejecutable (`python seed.py`) que limpia de forma controlada las tablas respetando la integridad referencial y puebla el estado inicial exacto exigido por la consigna.
  - Catálogo `estado_orden`: `PENDIENTE` (pos 1), `EN_REPARACION` (pos 2), `TERMINADA` (pos 3, es_final=True), `CANCELADA` (pos 4, es_final=True).
  - Usuarios y asignaciones de rol: `admin@example.com` (ADMIN), `admin2@example.com` (ADMIN), `recepcion@example.com` (RECEPCION), `mecanico@example.com` (MECANICO), `mecanico2@example.com` (MECANICO), `cliente@example.com` (CLIENTE), `nuevo@example.com` (MECANICO con `debe_cambiar_password = True`).
  - Clientes y vehículos: Laura (asociada a `cliente@example.com`) con 2 vehículos (`AC456EF` y otro); Jorge (sin usuario del sistema) con 1 vehículo.
  - Repuestos y stock inicial: Filtro de aceite (precio 8500.00, stock 10 con movimiento "Stock inicial"), Pastillas de freno (precio 32000.00, stock 4), Bujía (precio estándar, stock 2), Aceite por litro (precio 12000.00, stock 20).
  - Órdenes iniciales: Orden 1 (`PENDIENTE`, vehículo de Laura); Orden 2 (`EN_REPARACION`, vehículo de Jorge, asignada a `mecanico@example.com`, con 4 bujías requeridas para validar rechazo por stock insuficiente).
  - Históricos: Historial de precio del filtro de aceite (de 8000 a 8500); evento de seguridad inicial con actor `SISTEMA` ("Carga de los datos iniciales").
- **Script de validación de triggers (`test/solo_agregado.sql`)**:
  - Sentencias SQL directas (`UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`) ejecutables con cliente psql o GUI para confirmar que los disparadores PL/pgSQL abortan cualquier mutación (Caso oficial C-14 / RN-15).
- **Batería interactiva de pruebas HTTP en `test/*.http`**:
  - `01_health.http`: Casos C-01 (`GET /health/live`) y C-02 (`GET /health/ready`).
  - `02_auth.http`: Casos C-03 (auto-registro atómico y conflicto 409), C-04 (login exitoso con Set-Cookie HttpOnly), C-05 (timing attacks y dummy hash), C-06 (rate limiting 429 con Retry-After), C-07 (debe_cambiar_password y 403 en grupo protegido), C-08 (invalidación de sesiones previas comparando `iat` con microsegundos).
  - `03_roles.http`: Casos C-09 (RBAC dinámico en DB y expiración de roles) y C-10 (autoprotección de ADMIN: auto-revocación 409 y último admin 409).
  - `04_clientes_vehiculos.http`: Casos C-11 (aislamiento de clientes en `/mis-vehiculos`), C-12 (CRUD clientes y vehículos, validación año 1950..2100 y re-alta de patente vendida), C-13 (bloqueo de baja con órdenes abiertas).
  - `05_repuestos.http`: Casos C-15 (alta, reposición de stock y rechazo de campo `stock` en PATCH con 422) y C-16 (trazabilidad obligatoria de cambios de precio en `historial_precio_repuesto`).
  - `06_ordenes.http`: Casos C-17 (creación, copiado de precios y cálculo de total en servidor), C-18 (transición de estados, consumo atómico de stock y rollback total ante stock insuficiente) y C-19 (cancelación y precedencia de validación 403 antes que 409).
- **Guía de ejecución y verificación E2E (`test/README.md`)**:
  - Documentación de cómo levantar la aplicación, sembrar los datos y ejecutar las pruebas manuales y automatizadas.
- **Suite de pruebas automatizadas Pytest (`tests/test_seed_and_e2e.py`)**:
  - Verificación en suite de tests de la ejecución y re-ejecución (idempotencia) de `seed.py` y comprobación de los datos resultantes.

## Capabilities

### New Capabilities
- `seed-and-test-suite`: Inicialización canónica de datos de prueba y batería de verificación integral de casos de uso C-01 a C-19 para la API del taller mecánico.

### Modified Capabilities
*(Ninguna; no se modifican requerimientos funcionales de los specs existentes)*

## Impact

- **Código nuevo**: `seed.py` en la raíz del proyecto.
- **Pruebas y scripts**: `test/01_health.http`, `test/02_auth.http`, `test/03_roles.http`, `test/04_clientes_vehiculos.http`, `test/05_repuestos.http`, `test/06_ordenes.http`, `test/solo_agregado.sql`, `test/README.md`, `tests/test_seed_and_e2e.py`.
- **Persistencia**: Idempotencia garantizada en `seed.py` para repoblar la base de datos local y de pruebas sin inconsistencias de claves foráneas.
- **Riesgo**: Ninguno sobre APIs ni modelos de producción existentes.
