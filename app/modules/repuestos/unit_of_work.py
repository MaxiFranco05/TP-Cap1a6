from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.repository import (
    HistorialPrecioRepuestoRepository,
    MovimientoStockRepository,
    RepuestoRepository,
)


class RepuestosUnitOfWork(UnitOfWork):
    """Unit of Work específico para el módulo de repuestos e inventario."""

    repuestos: RepuestoRepository
    movimientos_stock: MovimientoStockRepository
    historial_precios: HistorialPrecioRepuestoRepository

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repuestos = RepuestoRepository(session)
        self.movimientos_stock = MovimientoStockRepository(session)
        self.historial_precios = HistorialPrecioRepuestoRepository(session)

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.repuestos = RepuestoRepository(self.session)
        self.movimientos_stock = MovimientoStockRepository(self.session)
        self.historial_precios = HistorialPrecioRepuestoRepository(self.session)
        return self
