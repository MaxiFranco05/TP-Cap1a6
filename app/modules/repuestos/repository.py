from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)


class RepuestoRepository(SoftDeleteRepository[Repuesto]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Repuesto)

    def _apply_search_filter(self, stmt: Any, q: str | None) -> Any:
        stmt = stmt.where(self._active_clause())
        if q is not None and q.strip() != "":
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(Repuesto.descripcion.ilike(pattern))  # type: ignore[attr-defined]
        return stmt

    async def get_by_codigo(self, codigo: str) -> Repuesto | None:
        stmt = (
            select(Repuesto)
            .where(Repuesto.codigo == codigo)
            .where(self._active_clause())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def search_active(
        self,
        q: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Repuesto]:
        stmt = self._apply_search_filter(select(Repuesto), q)
        stmt = stmt.order_by(Repuesto.id.asc()).offset(offset).limit(limit)  # type: ignore[union-attr]
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, q: str | None = None) -> int:
        stmt = self._apply_search_filter(
            select(func.count()).select_from(Repuesto),
            q,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


class MovimientoStockRepository(BaseRepository[MovimientoStock]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MovimientoStock)

    async def list_by_repuesto_id(self, repuesto_id: int) -> list[MovimientoStock]:
        stmt = (
            select(MovimientoStock)
            .where(MovimientoStock.repuesto_id == repuesto_id)
            .order_by(MovimientoStock.id.asc())  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class HistorialPrecioRepuestoRepository(BaseRepository[HistorialPrecioRepuesto]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HistorialPrecioRepuesto)

    async def list_by_repuesto_id(
        self, repuesto_id: int
    ) -> list[HistorialPrecioRepuesto]:
        stmt = (
            select(HistorialPrecioRepuesto)
            .where(HistorialPrecioRepuesto.repuesto_id == repuesto_id)
            .order_by(HistorialPrecioRepuesto.id.asc())  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
