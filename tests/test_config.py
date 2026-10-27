import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_settings_loaded_with_valid_values():
    settings = Settings(
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        POSTGRES_HOST="db_host",
        POSTGRES_PORT=5433,
        JWT_SECRET_KEY="test_secret_key",
        JWT_ALGORITHM="HS256",
        JWT_EXPIRATION_SECONDS=3600,
        COOKIE_SECURE=True,
        BCRYPT_ROUNDS=10,
        BCRYPT_MAX_CONCURRENCY=2,
        DB_POOL_SIZE=5,
        SQL_ECHO=True,
    )
    assert settings.POSTGRES_USER == "test_user"
    assert settings.POSTGRES_PASSWORD == "test_password"
    assert settings.POSTGRES_DB == "test_db"
    assert settings.POSTGRES_HOST == "db_host"
    assert settings.POSTGRES_PORT == 5433
    assert settings.JWT_SECRET_KEY == "test_secret_key"
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_EXPIRATION_SECONDS == 3600
    assert settings.COOKIE_SECURE is True
    assert settings.BCRYPT_ROUNDS == 10
    assert settings.BCRYPT_MAX_CONCURRENCY == 2
    assert settings.DB_POOL_SIZE == 5
    assert settings.SQL_ECHO is True


def test_settings_default_values():
    settings = Settings(
        POSTGRES_USER="taller_user",
        POSTGRES_PASSWORD="secure_password",
        POSTGRES_DB="taller_db",
        JWT_SECRET_KEY="another_secret",
    )
    assert settings.POSTGRES_HOST == "localhost"
    assert settings.POSTGRES_PORT == 5432
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_EXPIRATION_SECONDS == 1800
    assert settings.COOKIE_SECURE is False
    assert settings.BCRYPT_ROUNDS == 12
    assert settings.BCRYPT_MAX_CONCURRENCY == 4
    assert settings.DB_POOL_SIZE == 10
    assert settings.SQL_ECHO is False


def test_computed_database_url():
    settings = Settings(
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="mypassword",
        POSTGRES_DB="workshop",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5432,
        JWT_SECRET_KEY="secret",
    )
    expected_url = "postgresql+asyncpg://app_user:mypassword@127.0.0.1:5432/workshop"
    assert settings.DATABASE_URL == expected_url


def test_missing_postgres_password_raises_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            POSTGRES_USER="app_user",
            POSTGRES_DB="workshop",
            JWT_SECRET_KEY="secret",
            _env_file=None,
        )
    errors = exc_info.value.errors()
    assert any("POSTGRES_PASSWORD" in str(err) or "postgres_password" in str(err).lower() for err in errors)


def test_missing_jwt_secret_key_raises_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="mypassword",
            POSTGRES_DB="workshop",
            _env_file=None,
        )
    errors = exc_info.value.errors()
    assert any("JWT_SECRET_KEY" in str(err) or "jwt_secret_key" in str(err).lower() for err in errors)
