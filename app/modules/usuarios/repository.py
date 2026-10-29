from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.repository import BaseRepository
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    RolEnum,
    Usuario,
)


class UsuarioRepository(BaseRepository[Usuario]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Usuario)

    async def get_by_email(self, email: str) -> Usuario | None:
        stmt = select(Usuario).where(Usuario.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AsignacionRol)

    async def get_active_roles_by_usuario_id(
        self,
        usuario_id: int,
        now: datetime | None = None,
    ) -> list[str]:
        now_dt = now or datetime.now(timezone.utc)
        stmt = (
            select(AsignacionRol.rol)
            .where(AsignacionRol.usuario_id == usuario_id)
            .where(AsignacionRol.revocada_en.is_(None))  # type: ignore[union-attr]
            .where(
                or_(
                    AsignacionRol.vence_en.is_(None),  # type: ignore[union-attr]
                    AsignacionRol.vence_en > now_dt,  # type: ignore[operator]
                )
            )
            .order_by(AsignacionRol.id)  # type: ignore[arg-type]
        )
        result = await self.session.execute(stmt)
        return [str(r) for r in result.scalars().all()]

    async def list_by_usuario_id(self, usuario_id: int) -> list[AsignacionRol]:
        stmt = (
            select(AsignacionRol)
            .where(AsignacionRol.usuario_id == usuario_id)
            .order_by(AsignacionRol.id.asc())  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_open_by_usuario_and_rol(
        self,
        usuario_id: int,
        rol: str,
    ) -> AsignacionRol | None:
        stmt = (
            select(AsignacionRol)
            .where(AsignacionRol.usuario_id == usuario_id)
            .where(AsignacionRol.rol == str(rol))
            .where(AsignacionRol.revocada_en.is_(None))  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count_other_active_admins(
        self,
        excluded_usuario_id: int,
        now: datetime | None = None,
    ) -> int:
        now_dt = now or datetime.now(timezone.utc)
        stmt = (
            select(func.count(func.distinct(AsignacionRol.usuario_id)))
            .select_from(AsignacionRol)
            .join(Usuario, AsignacionRol.usuario_id == Usuario.id)  # type: ignore[arg-type]
            .where(Usuario.activo.is_(True))  # type: ignore[attr-defined]
            .where(Usuario.id != excluded_usuario_id)
            .where(AsignacionRol.rol == str(RolEnum.ADMIN.value))
            .where(AsignacionRol.revocada_en.is_(None))  # type: ignore[union-attr]
            .where(
                or_(
                    AsignacionRol.vence_en.is_(None),  # type: ignore[union-attr]
                    AsignacionRol.vence_en > now_dt,  # type: ignore[operator]
                )
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


class IntentoAccesoRepository(BaseRepository[IntentoAcceso]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, IntentoAcceso)

    async def count_recent_failures(
        self,
        email: str,
        ip: str,
        since: datetime,
    ) -> int:
        last_success_stmt = (
            select(func.max(IntentoAcceso.cuando))
            .where(IntentoAcceso.email == email)
            .where(IntentoAcceso.ip == ip)
            .where(IntentoAcceso.exito.is_(True))  # type: ignore[attr-defined]
            .where(IntentoAcceso.cuando >= since)
        )
        last_success_res = await self.session.execute(last_success_stmt)
        last_success = last_success_res.scalar_one_or_none()

        count_stmt = (
            select(func.count())
            .select_from(IntentoAcceso)
            .where(IntentoAcceso.email == email)
            .where(IntentoAcceso.ip == ip)
            .where(IntentoAcceso.exito.is_(False))  # type: ignore[attr-defined]
            .where(IntentoAcceso.cuando >= since)
        )
        if last_success is not None:
            count_stmt = count_stmt.where(IntentoAcceso.cuando > last_success)

        res = await self.session.execute(count_stmt)
        return int(res.scalar_one())

    async def count_consecutive_failures_in_window(
        self,
        email: str,
        ip: str,
        window_seconds: int = 60,
        now: datetime | None = None,
    ) -> int:
        now_dt = now or datetime.now(timezone.utc)
        window_start = now_dt - timedelta(seconds=window_seconds)
        return await self.count_recent_failures(email, ip, since=window_start)


class EventoSeguridadRepository(BaseRepository[EventoSeguridad]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EventoSeguridad)

    async def list_paginated(self, offset: int, limit: int) -> list[EventoSeguridad]:
        stmt = (
            select(EventoSeguridad)
            .order_by(EventoSeguridad.id.desc())  # type: ignore[union-attr]
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
