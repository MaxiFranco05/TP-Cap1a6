# Design: C-03 Base Repositories and Unit of Work

## Context

Con las 13 tablas y las migraciones Alembic en su lugar (`C-02`), debemos construir la capa transaccional base (`app/core/repository.py` y `app/core/unit_of_work.py`) y el interceptor global de errores de base de datos en `main.py` (`RN-18`). El Ejercicio 6 de la consigna oficial (pág. 14, 20 puntos de la evaluación) define contratos muy precisos para las dos jerarquías de repositorios y para el ciclo de vida del `UnitOfWork`. Ver `proposal.md` para la motivación y `specs/persistence-uow/spec.md` para los requisitos normativos.

## Goals / Non-Goals

**Goals:**
- Implementar `BaseRepository[T]` recibiendo `(session: AsyncSession, model_cls: type[T])` en su constructor (porque los tipos genéricos se borran en tiempo de ejecución en Python) y exponiendo `get_by_id`, `get_all`, `count`, `add`, `update` y `delete` (más alias `get` y `list`).
- Implementar `SoftDeleteRepository[T](BaseRepository[T])` filtrando registros con `borrado_en IS NULL` y agregando `get_by_id_including_deleted` y `soft_delete` (métodos que no existen en `BaseRepository`).
- Implementar `ReadOnlyRepository[T]` sin heredar de `BaseRepository[T]` para catálogos con clave primaria no entera (`estado_orden`), ofreciendo sólo métodos de lectura (`get_by_pk`, `get_all`, `count`).
- Implementar `AbstractUnitOfWork` / `UnitOfWork` en `app/core/unit_of_work.py` como gestor de contexto asincrónico que confirma al salir sin error, revierte si sale con excepción, y **nunca cierra la sesión** (`session.close()`).
- Registrar manejadores de excepciones en `main.py` para `IntegrityError` y `DataError` (`RN-18`).

**Non-Goals:**
- Los repositorios y Units of Work específicos de cada módulo (`UsuariosUnitOfWork`, `ClientesUnitOfWork`, `RepuestosUnitOfWork`, `OrdenesUnitOfWork`) se implementan en sus respectivos changes (`C-04`..`C-08`) heredando de estas clases base.

## Decisions

### 1. Firmas exactas de `BaseRepository[T]` y `SoftDeleteRepository[T]` (Ejercicio 6)
- **Decisión**:
  - `BaseRepository.__init__(self, session: AsyncSession, model_cls: type[T])`: guarda `self.session` y `self.model_cls`.
  - Métodos obligatorios de `BaseRepository[T]`:
    - `async def get_by_id(self, entity_id: int, options: Sequence[ExecutableOption] | None = None) -> T | None`
    - `async def get_all(self, *, offset: int = 0, limit: int = 100, options: Sequence[ExecutableOption] | None = None) -> list[T]`
    - `async def count(self) -> int`
    - `async def add(self, instance: T) -> T`: hace `self.session.add(instance)` y `await self.session.flush()`, luego `await self.session.refresh(instance)` (o retorna `instance`). Nunca llama a `commit()`.
    - `async def update(self, instance: T) -> T`: hace `self.session.add(instance)` y `await self.session.flush()`. Nunca llama a `commit()`.
    - `async def delete(self, instance: T) -> None`: hace `await self.session.delete(instance)` y `await self.session.flush()`. Nunca llama a `commit()`.
  - Alias adicionales (`get`, `list`) que delegan a `get_by_id` y `get_all` para mantener compatibilidad ergonómica.
  - `SoftDeleteRepository[T](BaseRepository[T])`:
    - Sobrescribe `get_by_id`, `get_all` y `count` agregando `.where(self.model_cls.borrado_en.is_(None))`.
    - Agrega `async def get_by_id_including_deleted(self, entity_id: int, options: Sequence[ExecutableOption] | None = None) -> T | None`.
    - Agrega `async def soft_delete(self, instance_or_id: T | int) -> T | None` que asigna `borrado_en = datetime.now(timezone.utc)` y ejecuta `await self.session.flush()`.
- **Justificación**: Cumple palabra por palabra con el Ejercicio 6 de la consigna (pág. 14).

### 2. Repositorio de Catálogo de Sólo Lectura Independiente (`ReadOnlyRepository[T]`)
- **Decisión**: Definir `ReadOnlyRepository[T]` en `app/core/repository.py` como una clase independiente que **no** hereda de `BaseRepository[T]`. Recibe `(session: AsyncSession, model_cls: type[T], pk_attr: str = "codigo")` y sólo expone métodos de lectura (`get_by_pk` / `get`, `get_all` / `list`, `count`), verificándose en tests que `hasattr(repo, "add")`, `hasattr(repo, "update")` y `hasattr(repo, "delete")` sean `False`.
- **Justificación**: El Ejercicio 6 exige explícitamente: *"El catálogo tiene un repositorio propio de sólo lectura que no hereda de BaseRepository: su clave primaria no es id y desde la API no se escribe, así que heredar le daría add, update y delete que no debe ofrecer"*.

### 3. `UnitOfWork` Base que NO cierra la sesión
- **Decisión**:
  ```python
  class AbstractUnitOfWork(ABC):
      def __init__(self, session: AsyncSession) -> None:
          self.session = session

      async def __aenter__(self) -> Self:
          return self

      async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
          if exc_type is not None:
              await self.rollback()
          else:
              await self.commit()

      async def commit(self) -> None:
          await self.session.commit()

      async def rollback(self) -> None:
          await self.session.rollback()
  ```
  `UnitOfWork(AbstractUnitOfWork)` provee la implementación concreta base de la que heredarán los Units of Work de cada módulo. Ningún método llama a `self.session.close()`.
- **Justificación**: El Ejercicio 6 y la tabla de requisitos no funcionales (pág. 14 y 19) evalúan que el `UnitOfWork` confirme al salir, revierta con excepción y **no cierre la sesión**, ya que la sesión la crea y cierra `get_session`.

### 4. Traducción de `IntegrityError` y `DataError` en `main.py` (`RN-18`)
- **Decisión**: Registrar `@app.exception_handler(IntegrityError)` y `@app.exception_handler(DataError)` en `main.py`:
  - Inspeccionar el `sqlstate` (`pgcode`) de la excepción subyacente (`orig`) cuando esté disponible:
    - `23505` (`UniqueViolationError`) o `23503` (`ForeignKeyViolationError`): devuelve `JSONResponse(status_code=409, content={"detail": "Conflicto de integridad con los datos almacenados."})`.
    - `23514` (`CheckViolationError`): devuelve `JSONResponse(status_code=422, content={"detail": "Los datos enviados violan una restricción de dominio."})`.
    - Cualquier otro `IntegrityError` devuelve `409 Conflict` con mensaje genérico propio.
  - `DataError` devuelve `422 Unprocessable Content` con mensaje propio.
  - Nunca se interpola `str(exc)` ni `str(exc.orig)` en la respuesta JSON.
- **Justificación**: Cumple la Regla Dura #10 y `RN-18` (pág. 8 y 20).

## Risks / Trade-offs

- **[Risk] Exposición accidental de detalles del esquema en mensajes de error** → **Mitigation**: Mapear por código SQLSTATE o clase de excepción a mensajes estáticos de dominio y cubrirlo con tests que verifiquen que nombres de tablas/constraints no aparezcan en el body JSON.
