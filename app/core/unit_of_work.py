from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession


class AbstractUnitOfWork(ABC):
    """Gestor de contexto asincrónico base para transacciones (Ejercicio 6).

    Confirma al salir del bloque sin error, revierte si se sale con una excepción
    y NO cierra la sesión, porque no la creó (la crea y cierra get_session).
    """

    session: AsyncSession

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError


class UnitOfWork(AbstractUnitOfWork):
    """Implementación base concreta del Unit of Work sobre una AsyncSession compartida."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
