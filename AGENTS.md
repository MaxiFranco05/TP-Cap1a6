# Taller Mecánico API — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo **PRIMERO** que todo agente lee al ingresar al repositorio.
> Generado a partir de `knowledge-base/`, `CHANGES.md` y `.atl/skill-registry.md`. No editar a mano sin sincronizar ambos archivos.

---

## Stack Tecnológico

| Componente | Versión mínima | Uso en el proyecto |
|---|---|---|
| **Python** | 3.12 | Lenguaje de desarrollo backend. |
| **FastAPI** | 0.111 | Framework web asincrónico; todos los handlers con `async def`. |
| **SQLModel** | 0.0.24 | Modelos de base de datos combinando SQLAlchemy y Pydantic. |
| **SQLAlchemy** | 2.0 (asincrónico) | Motor relacional, sesión asincrónica (`AsyncSession`) y carga anticipada (`selectinload`). |
| **asyncpg** | 0.30 | Driver/controlador asincrónico para PostgreSQL. |
| **PostgreSQL** | 16 | Servidor relacional con soporte transaccional ACID y disparadores PL/pgSQL. |
| **Alembic** | 1.13 | Control de versiones y migraciones de DB con plantilla asincrónica. |
| **pydantic-settings** | 2.0 | Gestión tipada de variables de entorno mediante clase `Settings`. |
| **bcrypt** | 4.0 | Hashing seguro de contraseñas fuera del bucle de eventos. |
| **PyJWT** | 2.8 | Emisión y verificación de tokens firmados (`HS256`). |
| **uvicorn** | fastapi[standard] | Servidor ASGI para ejecución de la aplicación. |

Detalle completo: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---|---|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Entender propósito general, actores y alcance de los Capítulos 1 a 6. |
| [02_descripcion_general.md](knowledge-base/02_descripcion_general.md) | Arquitectura en 6 capas y matriz completa de endpoints (abierto vs protegido). |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Roles dinámicos en base de datos (`asignacion_rol`), vigencia y autoprotección. |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Diccionario de 13 tablas obligatorias, ERD Mermaid, índices parciales y `seed.py`. |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Las 20 reglas oficiales de la cátedra (RN-01 a RN-20). |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario (US-001 a US-012) por épica con criterios de aceptación. |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Diagramas de secuencia: login y timing attack, auto-registro con UoW y ciclo de órdenes. |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Patrones (UoW, repositorios, triggers sólo agregado) y variables de entorno. |
| [09_decisiones_y_supuestos.md](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones arquitectónicas (DD-01 a DD-08) y supuestos técnicos (SU-01 a SU-04). |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | Inconsistencias resueltas y preguntas abiertas priorizadas. |

---

## Skills Disponibles

Fuente de verdad: `.atl/skill-registry.md` (generado por `skill-registry`).

| Agente | Rol | Skills que carga |
|---|---|---|
| **Backend Core** | FastAPI / SQLModel / UoW / Modelos / Migraciones | `fastapi`, `fastapi-python`, `fastapi-patterns`, `sqlalchemy-alembic-expert-best-practices-code-review`, `postgresql-table-design`, `tdd` |
| **Backend Aux** | Testing asincrónico, Fixtures, Optimización de queries | `python-testing-patterns`, `postgresql-optimization`, `no-ai-slop` |
| **Orquestación** | OPSX / SDD / Documentación y Roadmap | `kb-creator`, `roadmap-generator`, `agents-md-generator`, `skill-registry` |

Cargá la skill correspondiente al contexto **ANTES** de escribir código.

> Los compact rules de cada skill los resuelve el orquestador desde `.atl/skill-registry.md` (generado por `skill-registry`; no versionado). Esta tabla solo mapea skill → rol.

---

## Roadmap de Changes

El plan operativo de implementación completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: 9 changes atómicos en 7 fases semánticas.
- **Camino crítico** (8 changes): `C-01 → C-02 → C-03 → C-04 → C-05 → C-07* → C-08 → C-09`.
- **Primer change**: `C-01` (`foundation-setup`).

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md), identificá las dependencias del change y los archivos listados en "Leer antes".

---

## Reglas Duras (Específicas del Proyecto)

> Reglas globales ya definidas en la configuración global (orquestador, governance, Strict TDD, engram): el proyecto las **hereda**, no se repiten acá.

Las siguientes 10 reglas son el contrato estricto del proyecto. Romper cualquiera de ellas constituye un defecto grave:

1. **Contratos Pydantic estrictos**: NUNCA schemas de entrada sin `extra="forbid"` → rechazar cualquier campo no declarado con HTTP 422.
2. **Actualizaciones parciales**: NUNCA aplicar campos no enviados en peticiones `PATCH` → usar siempre `model_dump(exclude_unset=True)`.
3. **Unit of Work y Repositorios**: NUNCA ejecutar `commit()` dentro de un repositorio → los repositorios sólo hacen `flush()`; el `commit()` y `rollback()` son potestad exclusiva del `UnitOfWork` mediante `async with`.
4. **Carga anticipada (Eager Loading)**: NUNCA usar carga perezosa (lazy loading) en relaciones leídas → usar siempre `selectinload` en el repositorio para garantizar un número fijo de consultas y evitar el problema N+1 (caso C-15).
5. **Autenticación por Cookie**: NUNCA exponer el token JWT en el cuerpo JSON de respuesta ni aceptar `Authorization: Bearer` en endpoints protegidos → transportar el token exclusivamente en la cookie `access_token` (`HttpOnly`, `SameSite=Lax`).
6. **Bcrypt fuera del Event Loop**: NUNCA invocar bcrypt directamente en el bucle asincrónico → ejecutarlo con `asyncio.to_thread` bajo un `asyncio.Semaphore`, validando en los esquemas la longitud máxima de 72 bytes para evitar errores 500 no controlados.
7. **Mitigación de Timing Attacks en Login**: NUNCA responder de inmediato si un correo no existe → verificar contra un hash ficticio precalculado para igualar los tiempos de respuesta y devolver el mismo mensaje genérico (RN-09).
8. **Control de Esquema con Alembic**: NUNCA usar `create_all` → el esquema se versiona con Alembic en 2 migraciones (la 001 autogenerada con tablas e índices parciales, y la 002 escrita a mano para los disparadores de sólo agregado en las 3 tablas históricas).
9. **Tipos de Moneda y Fechas**: NUNCA usar `float` para importes monetarios ni timestamps sin zona horaria → dinero siempre en `Decimal` en Python y `NUMERIC` en base de datos; fechas siempre con `timestamptz`, comparando `iat` con microsegundos (sin truncar a segundos) contra `password_cambiada_en`.
10. **Traducción de Errores de Base de Datos**: NUNCA filtrar excepciones internas de PostgreSQL (`IntegrityError`) al cliente → traducirlas a respuestas de dominio (409 Conflict o 422 Unprocessable Entity) sin exponer el mapa interno del esquema.

---

## Flujo de Trabajo

```
1. Leer la KB relevante (knowledge-base/)        → entender el dominio
2. Identificar el change en CHANGES.md           → respetar dependencias
3. /opsx:propose C-NN-nombre                     → proposal + design + specs + tasks
4. Implementar las tasks (cargando skills)       → respetando Strict TDD y las 10 reglas duras
5. /opsx:archive C-NN-nombre + marcar [x]        → cerrar el change
```

Aplicar TODAS las reglas duras en cada paso. Ante cualquier duda o conflicto entre documentos, las reglas duras prevalecen.
