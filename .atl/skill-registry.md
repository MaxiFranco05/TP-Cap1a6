# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

See `_shared/skill-resolver.md` for the full resolution protocol.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| When user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests | tdd | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\tdd\SKILL.md |
| When writing Python tests, setting up test suites, or implementing testing best practices | python-testing-patterns | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\python-testing-patterns\SKILL.md |
| When building or reviewing FastAPI apps — Pydantic schemas, dependencies, async handlers, auth, or tests | fastapi-patterns | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\fastapi-patterns\SKILL.md |
| When working with FastAPI APIs, Pydantic models, dependencies, streaming responses, and serving frontend apps | fastapi | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\fastapi\SKILL.md |
| When implementing FastAPI APIs and asynchronous Python backend operations | fastapi-python | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\fastapi-python\SKILL.md |
| Tasks involving SQLAlchemy ORM, Alembic migrations, database schema changes, or query optimization | sqlalchemy-alembic-expert-best-practices-code-review | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\sqlalchemy-alembic-expert-best-practices-code-review\SKILL.md |
| When designing or reviewing a PostgreSQL-specific schema, choosing column types, keys, constraints, or indexes | postgresql-table-design | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\postgresql-table-design\SKILL.md |
| When optimizing PostgreSQL queries, using advanced data types (JSONB, arrays), full-text search, or performance tuning | postgresql-optimization | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\postgresql-optimization\SKILL.md |
| When the user wants documentation/text clearer, more direct, less AI-sounding, or asks to audit writing quality | no-ai-slop | c:\Users\maxif\OneDrive\Facultad\PROG3\Programación\TP_Cap1a6\.agents\skills\no-ai-slop\SKILL.md |
| When building new FastAPI applications, structuring modules, or setting up backend API architectures | fastapi-templates | C:\Users\maxif\.agents\skills\fastapi-templates\SKILL.md |
| Before writing or modifying database schema, migrations, indexes, triggers, connection pooling, or query optimization in Postgres | supabase-postgres-best-practices | C:\Users\maxif\.agents\skills\supabase-postgres-best-practices\SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### tdd
- Test behavior through public interfaces (seams), never test internal methods or private state
- Agree on test seams before writing tests; no tests against unconfirmed internal seams
- Red-Green-Refactor loop: write the failing test first, then minimal code to pass; never write production code before a test
- Work in vertical slices (tracer bullets): one test -> one implementation -> repeat; no horizontal bulk slicing
- Never write tautological assertions (`expect(add(a, b)).toBe(a + b)`); use independent known-good values or specs
- Keep tests decoupled from implementation details; refactoring internal code must never break passing tests
- Respect domain vocabulary from knowledge base/glossary in test names and assertions

### python-testing-patterns
- Follow AAA structure: Arrange, Act, Assert explicitly in every test case
- Standard test naming: `test_<unit>_<scenario>_<expected_outcome>` (e.g. `test_create_user_with_duplicate_email_raises_conflict`)
- Keep tests strictly isolated: zero shared mutable state between tests, use fixtures with appropriate scopes
- Use `pytest.fixture` with cleanup (`yield`) and dependency injection for DB sessions and test clients
- Use `pytest.mark.asyncio` for async tests; never mix sync and async test runners
- Use `freezegun` (`@freeze_time`) for time-dependent tests; avoid testing wall clock directly
- Use `unittest.mock.AsyncMock` for async boundaries and `side_effect` for retry/exception sequence testing
- Assert specific exception types and messages with `with pytest.raises(ExpectedException):`

### fastapi-patterns
- Use `Annotated` for all dependencies and route parameters: `db: Annotated[AsyncSession, Depends(get_db)]`
- Manage app lifecycle via `lifespan(app: FastAPI)` async context manager; no deprecated `@app.on_event`
- Configure application settings using `pydantic-settings` `BaseSettings` with `SettingsConfigDict(env_file=".env")`
- In Pydantic v2 schemas: use `model_config = {"from_attributes": True}` (replaces `orm_mode = True`)
- Route schemas must inherit `BaseModel` and set `extra = "forbid"` for strict input validation contracts
- Structure endpoints in layers: Router -> Service (business logic) -> Unit of Work / Repository -> SQLAlchemy Model
- Manage DB sessions with async generators: `async with AsyncSessionLocal() as session: yield session` with rollback on error
- Raise `HTTPException` with specific status codes (`status.HTTP_401_UNAUTHORIZED`, etc.) in router or service layers

### fastapi
- Always use `Annotated` for `Path`, `Query`, `Header`, and `Depends` declarations; avoid inline bare defaults
- Never use ellipsis (`...`) for required fields or path operations; omit default to mark required
- Define reusable type aliases for common dependencies (e.g., `CurrentUserDep = Annotated[User, Depends(get_user)]`)
- Declare router-level prefix, tags, and dependencies directly on `APIRouter(...)`, not in `include_router()`
- Always declare explicit return types on path operations (`async def get_item() -> ItemResponse:`) for serialization
- Use `response_model` explicitly when internal return model differs from the external public schema
- Do NOT use `ORJSONResponse` or `UJSONResponse`; Pydantic v2 handles Rust-level fast JSON serialization natively
- Never use `RootModel` or deprecated `__root__`; use standard models or `list[Item]` directly

### fastapi-python
- Use `async def` for any I/O bound endpoints (DB, HTTP calls, disk); use plain `def` only for CPU-bound or pure operations
- Follow RORO (Receive an Object, Return an Object) with typed Pydantic models; avoid raw untyped dictionaries
- Guard clauses and early returns: handle edge cases and validation failures first, place happy path last
- Never write unnecessary `else` branches after `return` or `raise`; use flat if-return flow
- Name variables descriptively with auxiliary verbs for booleans (`is_active`, `has_permission`, `can_cancel`)
- Use lowercase with underscores for all modules and file names (`user_service.py`, `order_router.py`)
- Keep handlers thin: delegate business rules, state transitions, and calculations to service classes

### sqlalchemy-alembic-expert-best-practices-code-review
- Index creation: always use `postgresql_concurrently=True` with autocommit blocks in Alembic to prevent locking
- Unique constraints: create concurrent index first, then attach constraint using the existing index
- Foreign keys: add foreign key constraints with `NOT VALID` first, then run `VALIDATE CONSTRAINT` in a subsequent step
- Check constraints: add check constraints with `NOT VALID` first, then validate separately to avoid full-table write locks
- Column type changes: never alter type directly in production; add new column, backfill asynchronously, then swap
- Limit non-unique composite indexes to maximum 3 columns; order columns by highest selectivity first
- Eliminate redundant indexes: never create an index that is a leftmost prefix of an existing composite index
- Ensure every frequent filter, join condition, and foreign key column has a supporting index

### postgresql-table-design
- Primary keys: prefer `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`; avoid legacy `SERIAL`
- Money and currency: ALWAYS use `NUMERIC(p, s)`; NEVER use `FLOAT`, `DOUBLE PRECISION`, or `MONEY`
- Timestamps: ALWAYS use `TIMESTAMPTZ` (`TIMESTAMP WITH TIME ZONE`); NEVER use plain `TIMESTAMP` without timezone
- Strings: use `TEXT` with optional `CHECK (LENGTH(val) <= N)` instead of `VARCHAR(N)` or `CHAR(N)`
- Foreign keys: PostgreSQL DOES NOT auto-index foreign key columns; manually add index on every FK referencing column
- Naming: strictly lowercase `snake_case` for tables, columns, and constraints; avoid quoted mixed-case identifiers
- Unique nulls: use `UNIQUE NULLS NOT DISTINCT` (PG15+) when only a single NULL value should be permitted
- Normalization: normalize to 3NF by default; denormalize only with measured read performance justification

### postgresql-optimization
- JSONB: index semi-structured JSONB columns with GIN (`USING gin(data)`); use `@>` containment operators for index scans
- Arrays: use PostgreSQL array types (`TEXT[]`) with `ANY(arr)` or `&&` overlap operators, backed by GIN indexes
- Window functions: use `SUM(...) OVER (PARTITION BY ... ORDER BY ...)` and `DENSE_RANK()` for complex analytics in DB
- Full-text search: use `tsvector` generated columns with GIN indexes and `plainto_tsquery()` with `ts_rank`
- Dead tuples & MVCC: frequent updates leave dead tuples; design narrow updateable columns or separate volatile attributes
- Optimize queries using `EXPLAIN (ANALYZE, BUFFERS)`: watch for sequential scans on large tables and high buffer reads
- Pagination: prefer keyset/cursor-based pagination (`WHERE id > :last_id LIMIT :n`) over large `OFFSET` values

### no-ai-slop
- Never use AI-slop buzzwords: delve, foster, leverage, utilize, facilitate, empower, streamline, robust, cutting-edge, tapestry
- Cut empty throat-clearing openers: "Here's the thing", "Let me be clear", "The uncomfortable truth is", "In order to"
- Avoid faux-insight setups and dramatic colon reveals: rewrite dramatic one-liners as clear, direct, informative sentences
- Replace weak passive verb constructions with direct active voice ("The service rejects expired tokens")
- Be concrete and specific: replace vague adjectives with exact metrics, figures, mechanisms, and real code entities
- Avoid rhetorical questions, mic-drop conclusions, and summary-recap endings ("In conclusion...", "Ultimately...")
- Keep sentences and paragraphs grounded: do not use em dashes as stylistic crutches; maintain technical precision

### fastapi-templates
- Adopt modular layout: `app/routers/`, `app/services/`, `app/models/`, `app/schemas/`, `app/core/`, `app/dependencies.py`
- Centralize app creation in a factory function `create_app() -> FastAPI` with lifespan and registered middleware
- Decouple router endpoints from direct database access: routes call services, services use UoW / repositories
- Manage environment variables via `core/config.py` with typed fields, default fallbacks, and `.env` parsing
- Configure async SQLAlchemy session factory with `expire_on_commit=False` and connection pool recycling
- Provide centralized `HTTPException` handlers and validation error formatters in app setup
- Structure test suite with `conftest.py` providing `AsyncClient` wired to dependency-overridden `get_db`

### supabase-postgres-best-practices
- Missing indexes: identify and add indexes for all columns used in `WHERE`, `ORDER BY`, and `JOIN` clauses
- Partial indexes: index only active or queried row subsets with `WHERE status = 'active'` to reduce index bloat
- Connection pooling: reuse database connection pools; avoid opening and tearing down connections per request
- Transaction scope: keep database transactions as short as possible; never perform external API calls or hashing inside transactions
- Lock contention: avoid table-level locks; use `NOWAIT` or `SKIP LOCKED` when queuing or consuming concurrent work
- Eliminate N+1 queries: eager-load relations with `selectinload` or `joinedload` in SQLAlchemy; avoid lazy loading in async loops
- Batch inserts and updates: use multi-row inserts (`INSERT INTO ... VALUES (...), (...)`) instead of single-row loops

## Project Conventions

| File | Path | Notes |
|------|------|-------|
| (none) | - | No convention files (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, etc.) detected yet in project root. Next phase `agent-instruction` will establish project standards. |

Read the convention files listed above for project-specific patterns and rules. All referenced paths have been extracted — no need to read index files to discover more.
