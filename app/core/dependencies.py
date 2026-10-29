from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any
from fastapi import Depends, HTTPException, Request, status
import jwt
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import AsignacionRol, Usuario


def get_uow(session: AsyncSession = Depends(get_session)) -> UnitOfWork:
    return UnitOfWork(session)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Usuario:
    """Extrae y verifica el usuario autenticado exclusivamente desde la cookie HttpOnly access_token.

    Nunca acepta Authorization: Bearer (Regla Dura #5).
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
        )

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido.",
            )
        usuario_id = int(sub)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
        ) from exc

    stmt = select(Usuario).where(Usuario.id == usuario_id)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if user is None or not user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo.",
        )

    # RN-07: comparar iat con microsegundos sin truncar contra password_cambiada_en
    iat_raw = payload.get("iat")
    if user.password_cambiada_en is not None and iat_raw is not None:
        iat_dt = datetime.fromtimestamp(float(iat_raw), tz=timezone.utc)
        if iat_dt < user.password_cambiada_en:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La sesión ha sido invalidada por un cambio de contraseña.",
            )

    return user


async def get_current_active_user(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    """Verifica que el usuario autenticado no tenga cambio obligatorio de contraseña pendiente (RN-06)."""
    if current_user.debe_cambiar_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debe cambiar su contraseña antes de acceder a este recurso.",
        )
    return current_user


def requiere_rol(
    *roles_permitidos: str,
) -> Callable[..., Coroutine[Any, Any, Usuario]]:
    """Dependencia que consulta en tiempo real los roles vigentes en asignacion_rol (RN-04)."""
    allowed = {str(r) for r in roles_permitidos}

    async def _role_checker(
        current_user: Usuario = Depends(get_current_active_user),
        session: AsyncSession = Depends(get_session),
    ) -> Usuario:
        now = datetime.now(timezone.utc)
        stmt = (
            select(AsignacionRol.rol)
            .where(AsignacionRol.usuario_id == current_user.id)
            .where(AsignacionRol.revocada_en.is_(None))  # type: ignore[union-attr]
            .where(
                or_(
                    AsignacionRol.vence_en.is_(None),  # type: ignore[union-attr]
                    AsignacionRol.vence_en > now,  # type: ignore[operator]
                )
            )
        )
        result = await session.execute(stmt)
        roles_vigentes = {str(r) for r in result.scalars().all()}
        if not roles_vigentes.intersection(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No posee permisos suficientes para realizar esta operación.",
            )
        return current_user

    return _role_checker


require_roles = requiere_rol
get_usuario_actual = get_current_user


async def get_current_cliente(
    current_user: Usuario = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session),
) -> Cliente | None:
    """Resuelve la ficha Cliente asociada al usuario autenticado en sesión (RN-17)."""
    if current_user.id is None:
        return None
    stmt = select(Cliente).where(Cliente.usuario_id == current_user.id)
    result = await session.execute(stmt)
    return result.scalars().first()
