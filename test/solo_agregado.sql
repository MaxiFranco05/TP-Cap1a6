-- ==============================================================================
-- Validación de Disparadores de Sólo Agregado (Append-Only) en PostgreSQL
-- Caso Oficial C-14 / Regla de Negocio RN-15
-- ==============================================================================
--
-- Las siguientes 6 sentencias demuestran que las 3 tablas históricas del sistema
-- son inmutables ante operaciones directas de modificación o eliminación:
--   - historial_estado_orden
--   - movimiento_stock
--   - historial_precio_repuesto
--
-- Cada sentencia DEBE fallar con la excepción PL/pgSQL:
--   "ERROR: Operación no permitida: la tabla <nombre> es de sólo agregado (append-only)"
--
-- Para ejecutar este script con psql:
--   psql -U taller_user -d taller_db -f test/solo_agregado.sql
-- ==============================================================================

\echo '--- [1/6] Intentando UPDATE sobre historial_estado_orden (Debe fallar) ---'
UPDATE historial_estado_orden
SET hasta_estado = 'CANCELADA'
WHERE id = 1;

\echo '--- [2/6] Intentando DELETE sobre historial_estado_orden (Debe fallar) ---'
DELETE FROM historial_estado_orden
WHERE id = 1;

\echo '--- [3/6] Intentando UPDATE sobre movimiento_stock (Debe fallar) ---'
UPDATE movimiento_stock
SET cantidad = 99
WHERE id = 1;

\echo '--- [4/6] Intentando DELETE sobre movimiento_stock (Debe fallar) ---'
DELETE FROM movimiento_stock
WHERE id = 1;

\echo '--- [5/6] Intentando UPDATE sobre historial_precio_repuesto (Debe fallar) ---'
UPDATE historial_precio_repuesto
SET precio_nuevo = 99999.00
WHERE id = 1;

\echo '--- [6/6] Intentando DELETE sobre historial_precio_repuesto (Debe fallar) ---'
DELETE FROM historial_precio_repuesto
WHERE id = 1;
