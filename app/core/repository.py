from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption
from sqlmodel import SQLModel

T = TypeVar("T", bound=SQLModel)


class BaseRepository(Generic[T]):
    """Repositorio genérico base.

    Recibe en su constructor la sesión y la clase del modelo porque los genéricos
    se borran en tiempo de ejecución (Ejercicio 6).
    Ningún método confirma la transacción: las escrituras hacen flush(), nunca commit().
    """

    def __init__(self, session: AsyncSession, model_cls: type[T]) -> None:
        self.session = session
        self.model_cls = model_cls

    async def get_by_id(
        self,
        entity_id: int,
        options: Sequence[ExecutableOption] | None = None,
    ) -> T | None:
        stmt = select(self.model_cls).where(getattr(self.model_cls, "id") == entity_id)
        if options:
            stmt = stmt.options(*options)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get(
        self,
        entity_id: int,
        options: Sequence[ExecutableOption] | None = None,
    ) -> T | None:
        return await self.get_by_id(entity_id, options=options)

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        options: Sequence[ExecutableOption] | None = None,
    ) -> list[T]:
        stmt = select(self.model_cls).offset(offset).limit(limit)
        if options:
            stmt = stmt.options(*options)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        options: Sequence[ExecutableOption] | None = None,
    ) -> list[T]:
        return await self.get_all(offset=skip, limit=limit, options=options)

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model_cls)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def add(self, instance: T) -> T:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: T) -> T:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: T) -> None:
        await self.session.delete(instance)
        await self.session.flush()


class SoftDeleteRepository(BaseRepository[T], Generic[T]):
    """Repositorio con soporte de borrado lógico.

    Hereda de BaseRepository[T], filtra los dados de baja (borrado_en IS NULL)
    y agrega get_by_id_including_deleted y soft_delete (Ejercicio 6).
    """

    def _active_clause(self) -> Any:
        return getattr(self.model_cls, "borrado_en").is_(None)

    async def get_by_id(
        self,
        entity_id: int,
        options: Sequence[ExecutableOption] | None = None,
    ) -> T | None:
        stmt = (
            select(self.model_cls)
            .where(getattr(self.model_cls, "id") == entity_id)
            .where(self._active_clause())
        )
        if options:
            stmt = stmt.options(*options)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id_including_deleted(
        self,
        entity_id: int,
        options: Sequence[ExecutableOption] | None = None,
    ) -> T | None:
        stmt = select(self.model_cls).where(getattr(self.model_cls, "id") == entity_id)
        if options:
            stmt = stmt.options(*options)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        options: Sequence[ExecutableOption] | None = None,
    ) -> list[T]:
        stmt = (
            select(self.model_cls)
            .where(self._active_clause())
            .offset(offset)
            .limit(limit)
        )
        if options:
            stmt = stmt.options(*options)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(
        self,
        skip: int = 0,
        limit: int = 100,
        options: Sequence[ExecutableOption] | None = None,
    ) -> list[T]:
        return await self.get_all(offset=skip, limit=limit, options=options)

    async def count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(self.model_cls)
            .where(self._active_clause())
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def soft_delete(self, instance_or_id: T | int) -> T | None:
        if isinstance(instance_or_id, int):
            instance = await self.get_by_id(instance_or_id)
            if instance is None:
                return None
        else:
            instance = instance_or_id

        setattr(instance, "borrado_en", datetime.now(timezone.utc))
        self.session.add(instance)
        await self.session.flush()
        return instance


class ReadOnlyRepository(Generic[T]):
    """Repositorio inmutable de sólo lectura para catálogos (RN-19, Ejercicio 6).

    NO hereda de BaseRepository[T]: su clave primaria no es id y desde la API
    no se escribe, por lo que no debe ofrecer add, update ni delete.
    """

    def __init__(
        self,
        session: AsyncSession,
        model_cls: type[T],
        pk_attr: str = "codigo",
    ) -> None:
        self.session = session
        self.model_cls = model_cls
        self.pk_attr = pk_attr

    async def get_by_pk(self, pk_value: Any) -> T | None:
        stmt = select(self.model_cls).where(
            getattr(self.model_cls, self.pk_attr) == pk_value
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get(self, pk_value: Any) -> T | None:
        return await self.get_by_pk(pk_value)

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by_attr: str | None = None,
    ) -> list[T]:
        stmt = select(self.model_cls)
        if order_by_attr is not None and hasattr(self.model_cls, order_by_attr):
            stmt = stmt.order_by(getattr(self.model_cls, order_by_attr))
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by_attr: str | None = None,
    ) -> list[T]:
        return await self.get_all(offset=skip, limit=limit, order_by_attr=order_by_attr)

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model_cls)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
