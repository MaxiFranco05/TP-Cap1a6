from abc import ABC, abstractmethod
from types import TracebackType
from typing import TYPE_CHECKING, Self
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
    from app.modules.repuestos.repository import (
        HistorialPrecioRepuestoRepository,
        MovimientoStockRepository,
        RepuestoRepository,
    )
    from app.modules.usuarios.repository import (
        AsignacionRolRepository,
        EventoSeguridadRepository,
        IntentoAccesoRepository,
        UsuarioRepository,
    )


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

    clientes: "ClienteRepository"
    vehiculos: "VehiculoRepository"
    usuarios: "UsuarioRepository"
    asignaciones_rol: "AsignacionRolRepository"
    intentos_acceso: "IntentoAccesoRepository"
    eventos_seguridad: "EventoSeguridadRepository"
    repuestos: "RepuestoRepository"
    movimientos_stock: "MovimientoStockRepository"
    historial_precios: "HistorialPrecioRepuestoRepository"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> Self:
        from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
        from app.modules.repuestos.repository import (
            HistorialPrecioRepuestoRepository,
            MovimientoStockRepository,
            RepuestoRepository,
        )
        from app.modules.usuarios.repository import (
            AsignacionRolRepository,
            EventoSeguridadRepository,
            IntentoAccesoRepository,
            UsuarioRepository,
        )

        self.clientes = ClienteRepository(self.session)
        self.vehiculos = VehiculoRepository(self.session)
        self.usuarios = UsuarioRepository(self.session)
        self.asignaciones_rol = AsignacionRolRepository(self.session)
        self.intentos_acceso = IntentoAccesoRepository(self.session)
        self.eventos_seguridad = EventoSeguridadRepository(self.session)
        self.repuestos = RepuestoRepository(self.session)
        self.movimientos_stock = MovimientoStockRepository(self.session)
        self.historial_precios = HistorialPrecioRepuestoRepository(self.session)
        return self

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
