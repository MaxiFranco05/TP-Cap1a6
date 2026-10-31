from collections.abc import Sequence
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.repository import BaseRepository, ReadOnlyRepository
from app.modules.clientes.models import Vehiculo
from app.modules.ordenes.models import EstadoOrden, HistorialEstadoOrden, ItemOrden, OrdenTrabajo


class EstadoOrdenRepository(ReadOnlyRepository[EstadoOrden]):
    """Repositorio de sólo lectura para el catálogo estado_orden (RN-19)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=EstadoOrden, pk_attr="codigo")

    async def list_ordered_by_posicion(self) -> list[EstadoOrden]:
        """Devuelve todos los estados ordenados por su campo 'posicion'."""
        return await self.get_all(offset=0, limit=100, order_by_attr="posicion")

    async def is_empty(self) -> bool:
        """Indica si el catálogo de estados está completamente vacío en la base."""
        return (await self.count()) == 0

    async def get_codigos_finales(self) -> list[str]:
        """Obtiene la lista de códigos de estados que marcan fin de ciclo (es_final=True)."""
        stmt = select(EstadoOrden.codigo).where(EstadoOrden.es_final.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ItemOrdenRepository(BaseRepository[ItemOrden]):
    """Repositorio para ítems de órdenes de trabajo."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=ItemOrden)

    async def list_by_orden_id(self, orden_id: int) -> list[ItemOrden]:
        stmt = (
            select(ItemOrden)
            .where(ItemOrden.orden_id == orden_id)
            .options(selectinload(ItemOrden.repuesto))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class HistorialEstadoOrdenRepository(BaseRepository[HistorialEstadoOrden]):
    """Repositorio de auditoría de sólo agregado para transiciones de órdenes (RN-15)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=HistorialEstadoOrden)

    async def list_by_orden_id(self, orden_id: int) -> list[HistorialEstadoOrden]:
        stmt = (
            select(HistorialEstadoOrden)
            .where(HistorialEstadoOrden.orden_id == orden_id)
            .order_by(HistorialEstadoOrden.cuando.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class OrdenTrabajoRepository(BaseRepository[OrdenTrabajo]):
    """Repositorio de órdenes de trabajo con precarga anticipada (selectinload) (Caso C-15)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model_cls=OrdenTrabajo)

    async def get_detalle(self, orden_id: int) -> OrdenTrabajo | None:
        """Obtiene el detalle completo de una orden con un número fijo de consultas SQL."""
        stmt = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(
                selectinload(OrdenTrabajo.vehiculo).selectinload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).selectinload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial),
                selectinload(OrdenTrabajo.mecanico),
                selectinload(OrdenTrabajo.estado_rel),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_paginado(
        self,
        *,
        estado: Optional[str] = None,
        vehiculo_ids: Optional[Sequence[int]] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[OrdenTrabajo], int]:
        """Lista órdenes aplicando filtros opcionales y retorna (items, total)."""
        base_query = select(OrdenTrabajo)
        count_query = select(func.count()).select_from(OrdenTrabajo)

        if estado:
            base_query = base_query.where(OrdenTrabajo.estado == estado)
            count_query = count_query.where(OrdenTrabajo.estado == estado)

        if vehiculo_ids is not None:
            base_query = base_query.where(OrdenTrabajo.vehiculo_id.in_(vehiculo_ids))
            count_query = count_query.where(OrdenTrabajo.vehiculo_id.in_(vehiculo_ids))

        # Precarga requerida para listar
        base_query = (
            base_query.options(
                selectinload(OrdenTrabajo.vehiculo).selectinload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).selectinload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial),
            )
            .order_by(OrdenTrabajo.id.desc())
            .offset(offset)
            .limit(limit)
        )

        total_res = await self.session.execute(count_query)
        total = int(total_res.scalar_one())

        items_res = await self.session.execute(base_query)
        items = list(items_res.scalars().all())

        return items, total

    async def count_open_by_vehiculo_id(
        self,
        vehiculo_id: int,
        final_estados: Sequence[str],
    ) -> int:
        """Cuenta órdenes abiertas de un vehículo (aquellas cuyo estado no es final) (RN-16)."""
        stmt = (
            select(func.count())
            .select_from(OrdenTrabajo)
            .where(
                OrdenTrabajo.vehiculo_id == vehiculo_id,
                ~OrdenTrabajo.estado.in_(final_estados),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
