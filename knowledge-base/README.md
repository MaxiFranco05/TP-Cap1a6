# Base de Conocimiento — Taller Mecánico API

Base de conocimiento estructurada y canónica para el proyecto **Taller mecánico: órdenes de trabajo, stock y acceso con FastAPI y PostgreSQL** (Programación III - UTN).

---

## Índice de Archivos

| # | Archivo | Temas cubiertos |
|:---:|---|---|
| 01 | [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito del sistema, objetivos por actor (Admin, Recepción, Mecánico, Cliente, Sistema), alcance y límites de la entrega. |
| 02 | [02_descripcion_general.md](02_descripcion_general.md) | Stack técnico oficial, arquitectura en 6 capas, integraciones y matriz completa de endpoints (grupo abierto vs protegido). |
| 03 | [03_actores_y_roles.md](03_actores_y_roles.md) | Roles dinámicos en base de datos con vigencia (`asignacion_rol`), matriz RBAC, autoprotección y cambio obligatorio de clave. |
| 04 | [04_modelo_de_datos.md](04_modelo_de_datos.md) | Dominios, ERD Mermaid, diccionario de 13 tablas obligatorias con restricciones/índices parciales y seed data inicial. |
| 05 | [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | Catálogo formal de las 20 reglas de negocio oficiales (RN-01 a RN-20) clasificadas por dominio funcional. |
| 06 | [06_funcionalidades.md](06_funcionalidades.md) | Historias de usuario (US-001 a US-012) organizadas por épica con criterios de aceptación y reglas asociadas. |
| 07 | [07_flujos_principales.md](07_flujos_principales.md) | Diagramas de secuencia y flujos paso a paso: Auth y timing attacks, auto-registro con UoW, ciclo de órdenes y cambio de contraseña. |
| 08 | [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones de diseño (UoW, Repositorios, Sólo agregado), estructura obligatoria de directorios, seguridad y variables de entorno. |
| 09 | [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | Decisiones de arquitectura documentadas (DD-01 a DD-08) y supuestos técnicos inferidos (SU-01 a SU-04). |
| 10 | [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | Inconsistencias resueltas, preguntas abiertas priorizadas y consolidación de campos de discovery para el orquestador. |

---

## Quick Start para Desarrolladores y Agentes

1. **Entender el Dominio y Alcance**: Leer [01_vision_y_objetivos.md](01_vision_y_objetivos.md) y [03_actores_y_roles.md](03_actores_y_roles.md).
2. **Entender la Persistencia y Datos**: Consultar [04_modelo_de_datos.md](04_modelo_de_datos.md).
3. **Comprender las Restricciones y Reglas**: Revisar [05_reglas_de_negocio.md](05_reglas_de_negocio.md).
4. **Respetar la Arquitectura**: Seguir la estructura y patrones en [02_descripcion_general.md](02_descripcion_general.md) y [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md).
5. **Verificar los Flujos de Trabajo**: Guiarse por [07_flujos_principales.md](07_flujos_principales.md) y [06_funcionalidades.md](06_funcionalidades.md).

---

## Resumen Ejecutivo

El sistema implementa una API REST asincrónica en Python 3.12 con FastAPI y PostgreSQL 16 para un taller mecánico. Se distingue por una arquitectura modular en 6 capas strictly-typed, control de transacciones multirrecurso mediante `UnitOfWork` asincrónico, autenticación por cookies `HttpOnly` y contraseñas hasheadas con `bcrypt` fuera del bucle de eventos, autorización dinámica en base de datos con vigencia y autoprotección, y tablas de sólo agregado inmutables protegidas por disparadores en PostgreSQL.
