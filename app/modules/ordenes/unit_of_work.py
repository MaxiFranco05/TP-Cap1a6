from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenTrabajoRepository,
)
from app.modules.repuestos.repository import (
    MovimientoStockRepository,
    RepuestoRepository,
)
from app.modules.usuarios.repository import UsuarioRepository


class OrdenesUnitOfWork(UnitOfWork):
    """Unit of Work para coordinar transacciones del módulo de órdenes de trabajo."""

    ordenes: OrdenTrabajoRepository
    items: ItemOrdenRepository
    historial: HistorialEstadoOrdenRepository
    estados: EstadoOrdenRepository
    repuestos: RepuestoRepository
    movimientos_stock: MovimientoStockRepository
    vehiculos: VehiculoRepository
    clientes: ClienteRepository
    usuarios: UsuarioRepository

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.ordenes = OrdenTrabajoRepository(session)
        self.items = ItemOrdenRepository(session)
        self.historial = HistorialEstadoOrdenRepository(session)
        self.estados = EstadoOrdenRepository(session)
        self.repuestos = RepuestoRepository(session)
        self.movimientos_stock = MovimientoStockRepository(session)
        self.vehiculos = VehiculoRepository(session)
        self.clientes = ClienteRepository(session)
        self.usuarios = UsuarioRepository(session)

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.ordenes = OrdenTrabajoRepository(self.session)
        self.items = ItemOrdenRepository(self.session)
        self.historial = HistorialEstadoOrdenRepository(self.session)
        self.estados = EstadoOrdenRepository(self.session)
        self.repuestos = RepuestoRepository(self.session)
        self.movimientos_stock = MovimientoStockRepository(self.session)
        self.vehiculos = VehiculoRepository(self.session)
        self.clientes = ClienteRepository(self.session)
        self.usuarios = UsuarioRepository(self.session)
        return self
