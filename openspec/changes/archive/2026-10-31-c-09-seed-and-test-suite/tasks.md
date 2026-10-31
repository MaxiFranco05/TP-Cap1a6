# Tasks: Poblado Canónico y Suite de Pruebas (C-09)

## 1. Script Canónico de Datos (`seed.py`)

- [x] 1.1 Implementar en `seed.py` la conexión asincrónica y la función de limpieza idempotente mediante `TRUNCATE TABLE ... RESTART IDENTITY CASCADE` de todas las tablas operativas e históricas, y verificar con test unitario de ejecución limpia.
- [x] 1.2 Implementar en `seed.py` la carga del catálogo de estados (`PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA`), los 7 usuarios canónicos con contraseña `Password123!` hasheada con bcrypt y sus roles vigentes (`ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`, y mecánico con `debe_cambiar_password = True`), verificando con test de persistencia.
- [x] 1.3 Implementar en `seed.py` la carga de clientes (Laura y Jorge) y sus vehículos, repuestos con stock inicial y movimientos en `movimiento_stock`, órdenes de trabajo (Orden 1 PENDIENTE y Orden 2 EN_REPARACION pidiendo 4 bujías), historial de precios del filtro de aceite y evento de auditoría inicial con actor `SISTEMA`, verificando con test de recuento e integridad.
- [x] 1.4 Implementar test de idempotencia en `tests/test_seed_and_e2e.py` que ejecute `seed.py` dos veces consecutivas comprobando que no ocurren colisiones ni violaciones de integridad referencial.

## 2. Script de Validación de Triggers y Suite Interactiva HTTP

- [x] 2.1 Construir `test/solo_agregado.sql` con las 6 sentencias `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` documentando el rechazo por disparadores PL/pgSQL (C-14 / RN-15) y verificar su formato SQL.
- [x] 2.2 Construir los archivos de prueba `test/01_health.http` (C-01, C-02), `test/02_auth.http` (C-03 a C-08) y `test/03_roles.http` (C-09, C-10) con variables `@baseUrl`, peticiones HTTP ordenadas, headers y respuestas esperadas documentadas.
- [x] 2.3 Construir los archivos de prueba `test/04_clientes_vehiculos.http` (C-11 a C-13), `test/05_repuestos.http` (C-15, C-16) y `test/06_ordenes.http` (C-17 a C-19) cubriendo la totalidad de los flujos de dominio restantes y validar sintaxis de peticiones.
- [x] 2.4 Redactar `test/README.md` detallando la guía de ejecución paso a paso, variables de entorno, usuarios sembrados con credenciales y matriz completa de trazabilidad de los casos oficiales C-01 a C-19.

## 3. Verificación Integral y Suite E2E

- [x] 3.1 Ejecutar la suite completa de pruebas de pytest (`tests/`) verificando que todos los tests unitarios, de integración y del seed pasen limpiamente al 100%.
