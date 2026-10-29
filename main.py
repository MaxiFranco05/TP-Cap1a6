import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import bcrypt
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
import app.modules.clientes.models  # noqa: F401
from app.modules.clientes.router import router as clientes_router
from app.modules.health.router import router as health_router
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401
from app.modules.usuarios.router import auth_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # Inicializar motor y fábrica de sesiones asincrónicas en app.state
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)

    # Precalcular hash ficticio fuera del event loop (mitigación de timing attack RN-09)
    salt = await asyncio.to_thread(bcrypt.gensalt, settings.BCRYPT_ROUNDS)
    dummy_hash_bytes = await asyncio.to_thread(bcrypt.hashpw, b"dummy_password", salt)
    app.state.dummy_hash = dummy_hash_bytes.decode("utf-8")

    yield

    # Apagado ordenado y cierre del pool de conexiones
    if hasattr(app.state, "engine") and app.state.engine is not None:
        await app.state.engine.dispose()


app = FastAPI(
    title="Taller Mecánico API",
    description="API REST asincrónica para gestión de taller mecánico, órdenes de trabajo, stock y acceso.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    """Traduce violaciones de integridad de PostgreSQL a respuestas de dominio (RN-18).

    Nunca filtra el texto interno de la base de datos ni el mapa del esquema.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)

    if sqlstate == "23514":
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Los datos enviados no cumplen las restricciones de validez del dominio."},
        )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "El recurso entra en conflicto con los datos existentes."},
    )


@app.exception_handler(DataError)
async def data_error_handler(_request: Request, _exc: DataError) -> JSONResponse:
    """Traduce errores de tipo/rango de datos en PostgreSQL a HTTP 422 (RN-18)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Formato o rango de datos inválido para la operación solicitada."},
    )


# Dos grupos canónicos de rutas
router_abierto = APIRouter()
router_abierto.include_router(health_router)
router_abierto.include_router(auth_router)

router_protegido = APIRouter()
router_protegido.include_router(clientes_router)

app.include_router(router_abierto)
app.include_router(router_protegido)
