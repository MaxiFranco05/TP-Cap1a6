import asyncio
from unittest.mock import AsyncMock, patch
import bcrypt
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from app.core.config import Settings
from main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_initializes_and_disposes_resources():
    test_app = FastAPI()
    test_settings = Settings(
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        JWT_SECRET_KEY="test_key",
        BCRYPT_ROUNDS=4,  # Fast rounds for test
    )

    with patch("main.get_settings", return_value=test_settings), \
         patch.object(AsyncEngine, "dispose", new_callable=AsyncMock) as mock_dispose:
        async with lifespan(test_app):
            # Engine and session_factory are set in app.state
            assert hasattr(test_app.state, "engine")
            assert isinstance(test_app.state.engine, AsyncEngine)

            assert hasattr(test_app.state, "session_factory")
            assert isinstance(test_app.state.session_factory, async_sessionmaker)
            assert test_app.state.session_factory.kw.get("expire_on_commit") is False

            # Dummy hash is precalculated
            assert hasattr(test_app.state, "dummy_hash")
            assert isinstance(test_app.state.dummy_hash, str)
            assert test_app.state.dummy_hash.startswith("$2")

            # Verify the dummy hash works with bcrypt
            is_valid = bcrypt.checkpw(b"dummy_password", test_app.state.dummy_hash.encode("utf-8"))
            assert is_valid is True

        # After exiting lifespan, dispose must have been called
        mock_dispose.assert_awaited_once()


def test_main_app_has_two_router_groups():
    # Verify main.py has router_abierto and router_protegido mounted
    from main import router_abierto, router_protegido
    assert router_abierto is not None
    assert router_protegido is not None
