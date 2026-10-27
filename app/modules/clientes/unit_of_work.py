from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository


class ClientesUnitOfWork(UnitOfWork):
    """Unit of Work específico para el módulo de clientes y vehículos."""

    clientes: ClienteRepository
    vehiculos: VehiculoRepository

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.clientes = ClienteRepository(session)
        self.vehiculos = VehiculoRepository(session)

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.clientes = ClienteRepository(self.session)
        self.vehiculos = VehiculoRepository(self.session)
        return self
