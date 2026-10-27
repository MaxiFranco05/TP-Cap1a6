# persistence-uow Specification

## Purpose
Defines the behavioral contract for the generic repository hierarchy (`BaseRepository[T]`, `SoftDeleteRepository[T]`, read-only catalog repository), the asynchronous `UnitOfWork` context manager, and global database exception translation (`RN-18`).

## Requirements

### Requirement: Generic BaseRepository Flush-Only Operations
The system SHALL provide a generic `BaseRepository[T]` receiving `(session: AsyncSession, model_cls: type[T])` in its constructor and exposing `get_by_id`, `get_all`, `count`, `add`, `update`, and `delete` (plus `get` and `list` aliases), where write operations execute `await session.flush()` and NEVER call `session.commit()`.

#### Scenario: Repository write flushes changes without committing the transaction
- **WHEN** `add`, `update`, or `delete` is invoked on a `BaseRepository[T]` instance
- **THEN** the repository executes `session.flush()` so primary keys and database defaults are populated, while the transaction remains uncommitted until the Unit of Work exits

### Requirement: SoftDeleteRepository Active Filtering and Soft Deletion
The system SHALL provide a `SoftDeleteRepository[T]` inheriting from `BaseRepository[T]` that filters out soft-deleted records (`borrado_en IS NULL`) in `get_by_id`, `get_all`, and `count`, and exclusively adds `get_by_id_including_deleted` and `soft_delete`.

#### Scenario: Soft-deleted entity is excluded from standard reads and included in historical reads
- **WHEN** `soft_delete` is called on a `SoftDeleteRepository[T]` for an active entity
- **THEN** `borrado_en` is set to the current UTC timestamp, `get_by_id` and `get_all` omit the entity, `count` decreases by one, and `get_by_id_including_deleted` still returns the entity

### Requirement: Read-Only Catalog Repository Isolation
The system SHALL provide a read-only catalog repository (`ReadOnlyRepository[T]`) that does NOT inherit from `BaseRepository[T]` and exposes only read operations (`get_by_codigo`, `get_all`, `count`), preventing any `add`, `update`, or `delete` calls from the API (`RN-19`).

#### Scenario: Catalog repository has no write methods
- **WHEN** a read-only catalog repository instance is inspected
- **THEN** it exposes read methods ordered or filtered as needed and does not define `add`, `update`, `delete`, or `soft_delete`

### Requirement: Asynchronous UnitOfWork Atomic Commit and Rollback Without Closing Session
The system SHALL provide an asynchronous `UnitOfWork` context manager (`async with uow:`) that commits the shared `AsyncSession` upon normal exit, rolls back the transaction if an exception is raised inside the block, and NEVER closes the session (`session.close()`).

#### Scenario: Multi-write block rolls back completely on failure and keeps session open
- **WHEN** multiple repository writes occur inside an `async with uow:` block and an exception is raised before exiting
- **THEN** `session.rollback()` is awaited, none of the writes persist in the database, and `session.close()` is not called by the Unit of Work

### Requirement: Safe Database Exception Translation (RN-18)
The system SHALL intercept `IntegrityError` and `DataError` globally in the FastAPI application and translate them into domain HTTP responses (`409 Conflict` or `422 Unprocessable Content`) with a clean Spanish message, never exposing raw PostgreSQL error strings, table/constraint names, or stack traces, and never returning `500 Internal Server Error` on invalid inputs.

#### Scenario: Unique constraint violation returns 409 without leaking schema details
- **WHEN** a database operation raises an `IntegrityError` due to a unique constraint or partial unique index conflict
- **THEN** the API responds with HTTP `409 Conflict` and a clean domain message that does not contain `asyncpg`, `DETAIL:`, `Key (`, or internal constraint identifiers
