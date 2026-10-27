from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo


class ClienteRepository(BaseRepository[Cliente]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Cliente)

    async def get_by_documento(self, documento: str) -> Cliente | None:
        stmt = select(Cliente).where(Cliente.documento == documento)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_usuario_id(self, usuario_id: int) -> Cliente | None:
        stmt = select(Cliente).where(Cliente.usuario_id == usuario_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id_with_vehiculos(self, cliente_id: int) -> Cliente | None:
        stmt = (
            select(Cliente)
            .where(Cliente.id == cliente_id)
            .options(
                selectinload(
                    Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None))  # type: ignore[arg-type]
                )
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()


class VehiculoRepository(SoftDeleteRepository[Vehiculo]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Vehiculo)

    async def get_by_patente_activa(self, patente: str) -> Vehiculo | None:
        stmt = (
            select(Vehiculo)
            .where(Vehiculo.patente == patente)
            .where(self._active_clause())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_cliente_id(self, cliente_id: int) -> list[Vehiculo]:
        stmt = (
            select(Vehiculo)
            .where(Vehiculo.cliente_id == cliente_id)
            .where(self._active_clause())
            .order_by(Vehiculo.id)  # type: ignore[arg-type]
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_open_orders(self, vehiculo_id: int) -> bool:
        """Verifica si el vehículo posee órdenes con estado no final (RN-16)."""
        subq = (
            select(OrdenTrabajo.id)
            .join(EstadoOrden, OrdenTrabajo.estado == EstadoOrden.codigo)  # type: ignore[arg-type]
            .where(OrdenTrabajo.vehiculo_id == vehiculo_id)
            .where(EstadoOrden.es_final.is_(False))  # type: ignore[attr-defined]
        )
        stmt = select(exists(subq))
        result = await self.session.execute(stmt)
        return bool(result.scalar_one())
