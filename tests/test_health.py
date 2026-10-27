import asyncio
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
from httpx import ASGITransport
from main import app
from app.core.database import get_session


@pytest.mark.asyncio
async def test_health_live_returns_200():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


@pytest.mark.asyncio
async def test_health_ready_returns_200_when_database_ok():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_database_fails():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=Exception("Database connection error"))

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "database unavailable"}
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_health_ready_returns_503_on_timeout():
    mock_session = AsyncMock()

    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(5)

    mock_session.execute = slow_execute

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "database unavailable"}
    finally:
        app.dependency_overrides.pop(get_session, None)
