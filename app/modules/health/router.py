import asyncio
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def health_live() -> dict[str, str]:
    """Sonda de liveness: confirma que el proceso web está en ejecución sin consultar la base de datos."""
    return {"status": "live"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def health_ready(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Sonda de readiness: valida conectividad activa con PostgreSQL ejecutando SELECT 1 con timeout."""
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "database unavailable"},
        )
