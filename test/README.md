# Suite de Pruebas y Verificación — Taller Mecánico API

Esta carpeta contiene la batería de pruebas interactivas (`.http`), el script SQL de validación de disparadores inmutables (`solo_agregado.sql`) y la guía oficial para verificar el cumplimiento íntegro de los 19 casos de prueba oficiales de la cátedra (Capítulos 1 a 6).

---

## 1. Puesta en Marcha

### Requisitos Previos
1. Base de datos PostgreSQL en ejecución (por defecto `127.0.0.1:5432`, base `taller_db`).
2. Entorno virtual activo con las dependencias instaladas:
   ```bash
   pip install -r requirements.txt
   ```
3. Archivo `.env` configurado (a partir de `env.example`).
4. Migraciones aplicadas al esquema de base de datos:
   ```bash
   alembic upgrade head
   ```

### Poblado Inicial Canónico
Para inicializar o reiniciar de forma determinística e idempotente todos los datos de prueba:
```bash
python seed.py
```
*(Limpia todas las tablas con `TRUNCATE ... RESTART IDENTITY CASCADE` y puebla catálogos, usuarios, clientes, vehículos, repuestos con stock inicial y órdenes canónicas).*

### Iniciar Servidor Web
```bash
uvicorn main:app --reload --port 8000
```

---

## 2. Usuarios Canónicos Sembrados

Todos los usuarios iniciales poseen la contraseña uniforme: **`Password123!`**.

| Email | Roles vigentes | Debe cambiar password | Propósito de prueba |
|---|---|---|---|
| `admin@example.com` | `ADMIN` | No | Administrador principal; gestión de usuarios, roles, catálogo y auditoría. |
| `admin2@example.com` | `ADMIN` | No | Segundo administrador; para verificar que un admin puede revocar a otro. |
| `recepcion@example.com` | `RECEPCION` | No | Recepcionista; alta de clientes, vehículos y creación de órdenes de trabajo. |
| `mecanico@example.com` | `MECANICO` | No | Mecánico titular; inicio de reparación y terminación con consumo de stock. |
| `mecanico2@example.com` | `MECANICO` | No | Mecánico auxiliar; para verificar que un mecánico no asignado no puede terminar la orden (403). |
| `cliente@example.com` | `CLIENTE` | No | Cliente Laura; autoservicio en `/mis-vehiculos`, `/mis-ordenes` y cancelación de orden propia. |
| `nuevo@example.com` | `MECANICO` | **Sí** | Mecánico recién ingresado; para verificar bloqueo 403 en grupo protegido hasta cambiar clave. |

---

## 3. Matriz de Trazabilidad de Casos de Prueba Oficiales

| Caso Oficial | Descripción resumida | Archivo de prueba | Reglas de negocio |
|---|---|---|---|
| **C-01** | Liveness probe (`GET /health/live`) responde 200 sin consultar BD | [`01_health.http`](01_health.http) | Monitoreo |
| **C-02** | Readiness probe (`GET /health/ready`) valida conectividad con PostgreSQL | [`01_health.http`](01_health.http) | Monitoreo |
| **C-03** | Auto-registro atómico de clientes y rechazo por conflicto 409 | [`02_auth.http`](02_auth.http) | RN-08 |
| **C-04** | Login con credenciales válidas y Set-Cookie HttpOnly | [`02_auth.http`](02_auth.http) | RN-05 |
| **C-05** | Mitigación de timing attack en login mediante dummy hash | [`02_auth.http`](02_auth.http) | RN-09 |
| **C-06** | Bloqueo por fuerza bruta (Rate limiting 429 con Retry-After) | [`02_auth.http`](02_auth.http) | RN-09 |
| **C-07** | Cambio obligatorio de contraseña (403 en rutas protegidas) | [`02_auth.http`](02_auth.http) | RN-06 |
| **C-08** | Invalidación de sesiones previas comparando microsegundos | [`02_auth.http`](02_auth.http) | RN-07 |
| **C-09** | RBAC dinámico en base de datos y expiración temporal de roles | [`03_roles.http`](03_roles.http) | RN-03, RN-04 |
| **C-10** | Autoprotección de ADMIN (auto-revocación 409 y último admin 409) | [`03_roles.http`](03_roles.http) | RN-04 |
| **C-11** | Aislamiento estricto de clientes en `GET /mis-vehiculos` | [`04_clientes_vehiculos.http`](04_clientes_vehiculos.http) | RN-17 |
| **C-12** | CRUD clientes, vehículos (año 1950..2100) y re-alta de patente vendida | [`04_clientes_vehiculos.http`](04_clientes_vehiculos.http) | RN-01, RN-02 |
| **C-13** | Bloqueo de baja de vehículo con órdenes abiertas (409 Conflict) | [`04_clientes_vehiculos.http`](04_clientes_vehiculos.http) | RN-02 |
| **C-14** | Disparadores PL/pgSQL de sólo agregado abortan mutaciones directas | [`solo_agregado.sql`](solo_agregado.sql) | RN-15 |
| **C-15** | Alta con stock inicial, reposición manual y rechazo de stock en PATCH (422) | [`05_repuestos.http`](05_repuestos.http) | RN-14 |
| **C-16** | Trazabilidad obligatoria de precios en `historial_precio_repuesto` | [`05_repuestos.http`](05_repuestos.http) | RN-20 |
| **C-17** | Composición atómica de orden, copiado de precios y total en servidor | [`06_ordenes.http`](06_ordenes.http) | RN-10 |
| **C-18** | Transición a EN_REPARACION, consumo atómico con BackgroundTasks y rollback por stock | [`06_ordenes.http`](06_ordenes.http) | RN-11, RN-13 |
| **C-19** | Precedencia de permisos (403 antes que 409 en cancelación) y `/mis-ordenes` | [`06_ordenes.http`](06_ordenes.http) | RN-12, RN-17 |

---

## 4. Validación de Disparadores SQL (Caso C-14)

Para verificar que los disparadores PL/pgSQL bloquean mutaciones directas en las 3 tablas históricas:
```bash
psql -U taller_user -d taller_db -f test/solo_agregado.sql
```
Cada una de las 6 sentencias (`UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`) abortará con error de disparador.

---

## 5. Ejecución Automatizada de la Suite de Pruebas

Para correr toda la suite de pruebas automatizadas del proyecto (unitarias, de integración, de seguridad y de siembra):
```bash
pytest
```
Todas las pruebas corren en memoria o contra base de datos transaccional con rollback automático.
