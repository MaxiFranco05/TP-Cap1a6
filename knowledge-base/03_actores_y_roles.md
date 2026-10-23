# Actores y Roles

## Actores del sistema

| Actor | Descripción | Mecanismo de interacción |
|---|---|---|
| **ADMIN** | Administrador del sistema y taller. Posee control total sobre usuarios, roles, catálogo de inventario, stock y seguridad. | Interfaz REST autenticada con rol `ADMIN` vigente en DB. |
| **RECEPCION** | Personal administrativo de mesa de entrada. Gestiona clientes, vehículos y abre órdenes de trabajo. | Interfaz REST autenticada con rol `RECEPCION` vigente en DB. |
| **MECANICO** | Operario de taller que ejecuta reparaciones físicas y consume repuestos en las órdenes de trabajo. | Interfaz REST autenticada con rol `MECANICO` vigente en DB. |
| **CLIENTE** | Dueño de uno o más vehículos atendidos por el taller. | Interfaz REST pública para registro y autenticada con rol `CLIENTE` para autoservicio. |
| **SISTEMA** | Actor de sistema utilizado para auditoría, carga inicial (`seed.py`) y eventos automáticos. | Identificador textual (`actor = "SISTEMA"`), no es un usuario con login. |

---

## Modelo de Roles Dinámicos en Base de Datos

A diferencia de modelos simplificados donde el rol es un campo estático en la tabla de usuarios, en este sistema:
1. **La tabla `usuario` no tiene columna `rol`**: Los roles se modelan en la tabla `asignacion_rol`.
2. **Vigencia en cada petición (RN-04)**: Los permisos se resuelven en tiempo real contra los roles vigentes (`vence_en IS NULL OR vence_en > NOW()` y `revocada_en IS NULL`).
3. **Roles en el JWT**: Los roles presentes en el token son únicamente informativos; revocar un rol en la base de datos surte efecto inmediato en la siguiente petición HTTP sin esperar a que el token expire.
4. **Historial inmutable**: Revocar un rol no borra el registro, sino que setea `revocada_en = NOW()`.
5. **Autoprotección (RN-05)**: Un administrador no puede revocarse a sí mismo el rol `ADMIN`, y el sistema nunca puede quedar sin al menos un `ADMIN` vigente.

---

## RBAC — Matriz de Permisos

| Recurso / Acción | ADMIN | RECEPCION | MECANICO | CLIENTE | Público |
|---|:---:|:---:|:---:|:---:|:---:|
| **Health (/health/live, /health/ready)** | ✔ | ✔ | ✔ | ✔ | ✔ |
| **Auth: Registro (/auth/registro)** | ✔ | ✔ | ✔ | ✔ | ✔ |
| **Auth: Login / Logout** | ✔ | ✔ | ✔ | ✔ | ✔ |
| **Auth: Perfil propio (/auth/yo)** | ✔ | ✔ | ✔ | ✔ | ✖ |
| **Auth: Cambiar contraseña (/auth/cambiar-password)** | ✔ | ✔ | ✔ | ✔ | ✖ |
| **Usuarios: Alta personal (/usuarios)** | ✔ | ✖ | ✖ | ✖ | ✖ |
| **Usuarios: Consultar/Asignar/Revocar Roles** | ✔ | ✖ | ✖ | ✖ | ✖ |
| **Eventos de seguridad (/eventos)** | ✔ | ✖ | ✖ | ✖ | ✖ |
| **Clientes: Alta y consulta (/clientes, /clientes/{id})** | ✔ | ✔ | ✖ | ✖ | ✖ |
| **Vehículos: Alta y baja (/clientes/{id}/vehiculos, /vehiculos/{id})** | ✔ | ✔ | ✖ | ✖ | ✖ |
| **Vehículos propios (/mis-vehiculos)** | ✖ | ✖ | ✖ | ✔ (sólo propios) | ✖ |
| **Repuestos: Listado y detalle (/repuestos, /repuestos/{id})** | ✔ | ✔ | ✔ | ✖ | ✖ |
| **Repuestos: Alta, edición PATCH, baja, reposición** | ✔ | ✖ | ✖ | ✖ | ✖ |
| **Repuestos: Ver movimientos e historial precios** | ✔ | ✖ | ✖ | ✖ | ✖ |
| **Órdenes: Crear orden (/ordenes)** | ✔ | ✔ | ✖ | ✖ | ✖ |
| **Órdenes: Listar órdenes (/ordenes)** | ✔ | ✔ | ✔ | ✖ | ✖ |
| **Órdenes: Ver detalle (/ordenes/{id})** | ✔ | ✔ | ✔ | ✔ (si es dueño) | ✖ |
| **Órdenes: Iniciar orden (/ordenes/{id}/iniciar)** | ✖ | ✖ | ✔ | ✖ | ✖ |
| **Órdenes: Terminar orden (/ordenes/{id}/terminar)** | ✔ | ✖ | ✔ (asignado) | ✖ | ✖ |
| **Órdenes: Cancelar orden (/ordenes/{id}/cancelar)** | ✔ | ✔ | ✖ | ✔ (si es dueño) | ✖ |
| **Catálogo de estados (/estados-orden)** | ✔ | ✔ | ✔ | ✔ | ✖ |
| **Órdenes propias (/mis-ordenes)** | ✖ | ✖ | ✖ | ✔ (sólo propias) | ✖ |

---

## Flujo de Cambio Obligatorio de Contraseña (RN-06)

Cuando un usuario tiene la bandera `debe_cambiar_password = True` (ej. tras el alta de personal por parte de un administrador o al crearse con clave provisoria):
1. **Acceso restringido**: El middleware o dependencia de control montada en el grupo protegido rechaza todas las peticiones con **403 Forbidden**.
2. **Rutas habilitadas**: El usuario sólo puede interactuar con el grupo abierto:
   - `/health/*` (rutas de salud).
   - `/auth/yo` (para verificar su estado).
   - `/auth/cambiar-password` (para actualizar su contraseña).
   - `/auth/logout` (para cerrar sesión).
3. **Invalidación de sesiones previas (RN-07)**: Al ejecutarse el cambio de clave exitoso, el campo `password_cambiada_en` se actualiza con precisión de microsegundos (`timestamptz`). Toda cookie o token cuyo `iat` sea anterior a esa marca de tiempo es inmediatamente rechazado con **401 Unauthorized**.
