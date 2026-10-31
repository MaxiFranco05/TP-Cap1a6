# Design: c-09-seed-and-test-suite

## Context

Este cambio final completa el monorepo implementando el script canónico de datos `seed.py`, la suite de archivos de prueba interactiva `test/*.http`, el script de verificación de disparadores `test/solo_agregado.sql` y las pruebas automatizadas de siembra e idempotencia en `tests/test_seed_and_e2e.py`. Toda la lógica de negocio, persistencia relacional, seguridad y endpoints de la API de taller mecánico ya fue implementada y testeada exhaustivamente a lo largo de los changes C-01 al C-08. Ver `proposal.md` para la motivación.

## Goals / Non-Goals

**Goals:**
- Implementar `seed.py` como un script autónomo e idempotente ejecutable mediante `python seed.py`, que limpie la base y siembre el estado canónico completo exigido por la cátedra.
- Garantizar que las secuencias autonuméricas se reinicien de modo que los IDs de entidades canónicas (como la Orden 1 y Orden 2, usuarios y clientes) sean predecibles para las pruebas.
- Producir `test/solo_agregado.sql` con 6 sentencias SQL directas (`UPDATE` y `DELETE` sobre las 3 tablas históricas) que demuestren fehacientemente el bloqueo por triggers PL/pgSQL (RN-15).
- Crear los 6 archivos `.http` temáticos cubriendo minuciosamente los 19 casos oficiales de prueba (C-01 a C-19) con ejemplos de petición, cookies y respuestas esperadas.
- Documentar en `test/README.md` las credenciales estándar de prueba, la secuencia recomendada de ejecución y la matriz de trazabilidad con los criterios de evaluación.
- Implementar `tests/test_seed_and_e2e.py` para asegurar que `seed.py` se ejecute sin errores en la suite automatizada de pytest y valide la idempotencia al ejecutarse dos veces seguidas.

**Non-Goals:**
- Modificar modelos de datos SQLModel ni agregar nuevas migraciones de Alembic (el esquema está cerrado y verificado en C-02).
- Modificar contratos de endpoints ni dependencias de FastAPI (todos los módulos C-01 a C-08 están operativos y pasando tests).

## Decisions

### 1. Limpieza de tablas e idempotencia en `seed.py`
- **Decisión**: Utilizar `TRUNCATE TABLE ... RESTART IDENTITY CASCADE` ejecutado mediante SQL crudo a través del motor asincrónico.
- **Razón**: `TRUNCATE TABLE ... CASCADE` en PostgreSQL:
  1. Elimina todos los registros de las tablas en una sola instrucción atómica sin violar restricciones de clave foránea.
  2. No dispara los triggers `BEFORE UPDATE OR DELETE` a nivel de fila (`rechazar_mutacion_solo_agregado()`), permitiendo limpiar las tablas históricas (`historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`) sin necesidad de deshabilitar disparadores.
  3. `RESTART IDENTITY` reinicia los contadores de secuencias autonuméricas (`SERIAL` / `IDENTITY`), garantizando que la primera orden sea `#1`, el primer usuario sea `#1`, etc., facilitando la ejecución de los scripts `.http`.
- **Alternativas consideradas**: `DELETE FROM` con desactivación de foreign keys o borrado manual en orden topológico (mucho más lento, y fallaría ante los triggers de sólo agregado a menos que se use `session_replication_role = 'replica'`).

### 2. Generación determinística de contraseñas de prueba
- **Decisión**: Fijar una contraseña uniforme y fácil de recordar para todos los usuarios sembrados: `Password123!`.
- **Razón**: Permite a cualquier evaluador o estudiante iniciar sesión con cualquiera de los 7 usuarios sin consultar tablas o hashes. El hash se calcula una sola vez con `bcrypt` durante la ejecución de `seed.py` (usando `Settings.BCRYPT_ROUNDS`), asegurando que todos los usuarios tengan hashes válidos y seguros.

### 3. Modularización de la suite interactiva `test/*.http`
- **Decisión**: Estructurar los casos de prueba en 6 archivos separados por dominio:
  - `01_health.http`: Casos C-01 y C-02 (liveness y readiness).
  - `02_auth.http`: Casos C-03 a C-08 (auto-registro, login con cookie, timing attacks, rate limiting, password obligatoria e invalidación de token).
  - `03_roles.http`: Casos C-09 y C-10 (RBAC dinámico y autoprotección de ADMIN).
  - `04_clientes_vehiculos.http`: Casos C-11 a C-13 (aislamiento en `/mis-vehiculos`, CRUD de flota y bloqueo de borrado con órdenes abiertas).
  - `05_repuestos.http`: Casos C-15 y C-16 (alta y reposición de repuestos, rechazo de stock en PATCH y trazabilidad de precios).
  - `06_ordenes.http`: Casos C-17 a C-19 (creación atómica, máquina de estados, consumo transaccional de stock con BackgroundTasks y cancelación con precedencia 403 vs 409).
- **Razón**: Permite ejecutar pruebas atómicas sin tener que recorrer un archivo gigante de más de mil líneas, y mapea de forma transparente cada caso con la consigna oficial.

## UI Mockups

Decision: no (no UI)

## Risks / Trade-offs

- **[Riesgo] Incompatibilidad de TRUNCATE con transacciones de sólo lectura o roles sin privilegios** → **Mitigación**: `seed.py` se ejecuta con el usuario de base de datos configurado en `DATABASE_URL` (`POSTGRES_USER`), que es el dueño del esquema.
- **[Riesgo] Triggers bloqueando la siembra** → **Mitigación**: Los disparadores son solo para `UPDATE` y `DELETE`; la inserción inicial (`INSERT`) de históricos en `seed.py` funciona normalmente.
