# seed-and-test-suite Specification

## Purpose

Provee el mecanismo oficial de inicialización determinística de datos de prueba (`seed.py`) y la batería integral de verificación interactiva y automatizada de los 19 casos de prueba oficiales de la cátedra para el taller mecánico.

## Requirements

### Requirement: Inicialización canónica e idempotente de la base de datos
El script `seed.py` SHALL limpiar e inicializar de forma determinística e idempotente la base de datos con todos los catálogos, usuarios, clientes, vehículos, repuestos, órdenes e historiales canónicos requeridos por los casos de prueba oficiales.

#### Scenario: Ejecución exitosa de seed en base limpia o preexistente
- **WHEN** un operador o test ejecuta `python seed.py` contra la base de datos PostgreSQL
- **THEN** el script limpia las tablas respetando claves foráneas, inserta los 7 usuarios canónicos con sus roles correspondientes, crea los clientes Laura y Jorge con sus vehículos, y finaliza con código de salida 0.

#### Scenario: Catálogo de estados inicializado en orden estricto
- **WHEN** finaliza la ejecución de `seed.py`
- **THEN** la tabla `estado_orden` contiene exactamente los estados `PENDIENTE` (1), `EN_REPARACION` (2), `TERMINADA` (3, final) y `CANCELADA` (4, final) ordenados por su posición.

#### Scenario: Repuestos y stock inicial con movimientos trazables
- **WHEN** finaliza la ejecución de `seed.py`
- **THEN** la tabla `repuesto` contiene filtro de aceite (precio 8500.00, stock 10), pastillas de freno (precio 32000.00, stock 4), bujías (stock 2) y aceite (precio 12000.00, stock 20), con sus movimientos iniciales asentados en `movimiento_stock` y el historial de precio del filtro registrado.

#### Scenario: Órdenes canónicas en estados pendiente y en reparación
- **WHEN** finaliza la ejecución de `seed.py`
- **THEN** la base contiene la Orden 1 (`PENDIENTE` sobre vehículo de Laura) y la Orden 2 (`EN_REPARACION` sobre vehículo de Jorge, asignada a `mecanico@example.com` con 4 bujías requeridas para validar falta de stock).

### Requirement: Verificación de disparadores de sólo agregado en PostgreSQL
El sistema SHALL proveer el script SQL `test/solo_agregado.sql` para comprobar que los disparadores PL/pgSQL abortan con error cualquier intento de mutación directa (`UPDATE` o `DELETE`) sobre las tablas históricas `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (RN-15).

#### Scenario: Rechazo de actualización o borrado en tablas de sólo agregado
- **WHEN** se ejecutan las sentencias `UPDATE` o `DELETE` contenidas en `test/solo_agregado.sql` contra PostgreSQL
- **THEN** el motor relacional aborta cada una de las 6 sentencias con una excepción de disparador, impidiendo cualquier alteración de registros históricos.

### Requirement: Batería interactiva de pruebas HTTP para casos oficiales C-01 a C-19
El sistema SHALL proveer una colección completa de archivos `.http` en el directorio `test/` documentando y permitiendo ejecutar de forma reproducible la totalidad de los 19 casos de prueba oficiales de la cátedra mediante clientes HTTP estándar.

#### Scenario: Cobertura completa de casos C-01 a C-19 en archivos http estructurados
- **WHEN** un desarrollador o evaluador revisa el directorio `test/`
- **THEN** encuentra los archivos `01_health.http`, `02_auth.http`, `03_roles.http`, `04_clientes_vehiculos.http`, `05_repuestos.http` y `06_ordenes.http` cubriendo con precisión los 19 casos de prueba oficiales con sus códigos de respuesta esperados.

#### Scenario: Documentación de ejecución y flujo integral en README de pruebas
- **WHEN** un evaluador consulta `test/README.md`
- **THEN** dispone de la secuencia ordenada de ejecución, variables de entorno, credenciales de los usuarios sembrados y correspondencia exacta de cada petición con las reglas de negocio y casos de prueba evaluados.
