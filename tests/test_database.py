import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from app.core.config import Settings
from app.core.database import create_engine, create_session_factory, get_session


def test_create_engine_returns_async_engine():
    settings = Settings(
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        JWT_SECRET_KEY="test_key",
        DB_POOL_SIZE=5,
        SQL_ECHO=False,
    )
    engine = create_engine(settings)
    assert isinstance(engine, AsyncEngine)
    assert engine.url.render_as_string(hide_password=False) == settings.DATABASE_URL


def test_create_session_factory_configured_with_expire_on_commit_false():
    settings = Settings(
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        JWT_SECRET_KEY="test_key",
    )
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    assert isinstance(session_factory, async_sessionmaker)
    assert session_factory.kw.get("expire_on_commit") is False


@pytest.mark.asyncio
async def test_get_session_yields_async_session():
    mock_session = AsyncMock(spec=AsyncSession)

    class DummyContextManager:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_factory = MagicMock(return_value=DummyContextManager())

    class DummyAppState:
        def __init__(self, session_factory):
            self.session_factory = session_factory

    class DummyApp:
        def __init__(self, state):
            self.state = state

    class DummyRequest:
        def __init__(self, app):
            self.app = app

    dummy_request = DummyRequest(app=DummyApp(state=DummyAppState(session_factory=mock_factory)))

    session_generator = get_session(dummy_request)
    session = await anext(session_generator)
    assert session is mock_session
    mock_factory.assert_called_once()
