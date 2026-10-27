import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import bcrypt
from fastapi import APIRouter, FastAPI
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.modules.health.router import router as health_router


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

# Dos grupos canónicos de rutas
router_abierto = APIRouter()
router_abierto.include_router(health_router)

router_protegido = APIRouter()

app.include_router(router_abierto)
app.include_router(router_protegido)
