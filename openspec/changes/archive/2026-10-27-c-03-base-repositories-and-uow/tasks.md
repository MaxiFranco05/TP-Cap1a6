# Tasks: C-03 Base Repositories and Unit of Work

## 1. Jerarquía de Repositorios (`BaseRepository`, `SoftDeleteRepository`, `ReadOnlyRepository`)

- [x] 1.1 Escribir tests unitarios y de integración en `tests/test_repository_uow.py` para `BaseRepository[T]`, `SoftDeleteRepository[T]` y `ReadOnlyRepository[T]`, verificando: constructor `(session, model_cls)`, ejecución exclusiva de `flush()` sin `commit()` en `add`/`update`/`delete`, filtrado de `borrado_en IS NULL`, existencia exclusiva de `get_by_id_including_deleted` y `soft_delete` en `SoftDeleteRepository`, precarga con `selectinload`, y que `ReadOnlyRepository` no herede de `BaseRepository` ni exponga métodos de escritura.
- [x] 1.2 Implementar `app/core/repository.py` con `BaseRepository[T]`, `SoftDeleteRepository[T]` y `ReadOnlyRepository[T]`, ejecutando `pytest tests/test_repository_uow.py` hasta que los tests de repositorios pasen en verde.

## 2. Gestor de Contexto Asincrónico `UnitOfWork`

- [x] 2.1 Ampliar `tests/test_repository_uow.py` con pruebas para `AbstractUnitOfWork` y `UnitOfWork`: confirmación (`commit()`) al salir del bloque `async with uow:` sin error, reversión atómica (`rollback()`) de múltiples escrituras cuando se lanza una excepción dentro del bloque, y verificación explícita de que `session.close()` nunca sea invocado por el Unit of Work.
- [x] 2.2 Implementar `app/core/unit_of_work.py` con `AbstractUnitOfWork` y `UnitOfWork`, verificando que los tests del Unit of Work pasen en verde.

## 3. Traducción Global de Errores de Persistencia (`RN-18`)

- [x] 3.1 Ampliar `tests/test_repository_uow.py` con pruebas HTTP para los manejadores globales de `IntegrityError` (409 en violaciones de unicidad / FK, 422 en `CHECK` violations) y `DataError` (422) en `main.py`, comprobando que la respuesta JSON nunca filtre texto interno de PostgreSQL (`asyncpg`, nombres de constraints, `DETAIL:`) ni devuelva HTTP 500.
- [x] 3.2 Registrar los exception handlers de `IntegrityError` y `DataError` en `main.py` y ejecutar toda la suite `pytest` verificando que el 100% de las pruebas pase en verde.
