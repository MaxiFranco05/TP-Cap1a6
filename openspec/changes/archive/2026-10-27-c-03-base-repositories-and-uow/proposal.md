# Proposal: C-03 Base Repositories and Unit of Work

## Why

Con el esquema relacional y las migraciones listos (`C-02`), el sistema necesita su capa de abstracción transaccional (`app/core/repository.py` y `app/core/unit_of_work.py`) y los manejadores globales de errores de persistencia en `main.py` (`RN-18`). Esto asegura que ningún repositorio confirme transacciones por su cuenta (`flush()` sin `commit()`), que el `UnitOfWork` agrupe atómicamente múltiples escrituras sin cerrar la sesión inyectada, y que ninguna violación de integridad (`IntegrityError` / `DataError`) filtre estructura interna de PostgreSQL ni termine en un HTTP 500.

## What Changes

- **Jerarquía de Repositorios en `app/core/repository.py` (Ejercicio 6)**:
  - `BaseRepository[T]`: Recibe `(session: AsyncSession, model_cls: type[T])` en su constructor y ofrece `get_by_id`, `get_all`, `count`, `add`, `update` y `delete` (más alias compatibles `get` y `list` para conveniencia de los módulos). `add`, `update` y `delete` ejecutan `await session.flush()`, **nunca** `commit()`.
  - `SoftDeleteRepository[T](BaseRepository[T])`: Filtra automáticamente las filas dadas de baja (`borrado_en IS NULL`) en `get_by_id`, `get_all` y `count`, y agrega exclusivamente `get_by_id_including_deleted` y `soft_delete` (que no existen en `BaseRepository`).
  - `ReadOnlyCatalogRepository[T]` (o clase base de sólo lectura para catálogos): No hereda de `BaseRepository` (su PK no es `id` y no debe exponer `add`, `update` ni `delete`).
- **Patrón Unit of Work en `app/core/unit_of_work.py` (Ejercicio 6)**:
  - Clase base `AbstractUnitOfWork` / `UnitOfWork`: Gestor de contexto asincrónico (`async with uow:`) que recibe la `AsyncSession` creada por `get_session`, confirma (`await session.commit()`) al salir del bloque sin excepción, revierte (`await session.rollback()`) si sale con excepción, y **no cierra la sesión** (`session.close()`), porque no la creó.
- **Traducción Global de Errores de Base de Datos en `main.py` (`RN-18`)**:
  - Manejador global de `IntegrityError` que traduce violaciones de unicidad (`23505` / unique constraint) a HTTP `409 Conflict` y violaciones de `CHECK` o clave foránea (`23514`, `23503`) a HTTP `409` / `422` con mensajes propios de dominio, sin exponer jamás el texto crudo de PostgreSQL ni el nombre de tablas/columnas internas.
  - Manejador global de `DataError` / `DBAPIError` de conversión para responder HTTP `422 Unprocessable Content` y evitar cualquier `500 Internal Server Error` ante entradas inválidas.

## Capabilities

### New Capabilities
- `persistence-uow`: Jerarquía de repositorios (`BaseRepository[T]`, `SoftDeleteRepository[T]`, repositorio de catálogo de sólo lectura), gestor de contexto transaccional `UnitOfWork` asincrónico y traducción segura de excepciones de base de datos (`RN-18`).

### Modified Capabilities
<!-- Ninguna capacidad existente cambia sus requisitos -->

## Impact

- **Nuevos módulos core**:
  - `app/core/repository.py`
  - `app/core/unit_of_work.py`
- **Archivos modificados**:
  - `main.py` (registro de exception handlers para `IntegrityError` y `DataError`)
- **Pruebas automatizadas**:
  - `tests/test_repository_uow.py`
