import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
import bcrypt
from fastapi import Request, Response
import jwt
from app.core.config import Settings, get_settings

ACCESS_TOKEN_COOKIE_NAME = "access_token"
MAX_BCRYPT_PASSWORD_BYTES = 72

_bcrypt_semaphore: asyncio.Semaphore | None = None
_bcrypt_semaphore_key: tuple[int, int] | None = None
_cached_dummy_hash: str | None = None


def _get_bcrypt_semaphore(max_concurrency: int) -> asyncio.Semaphore:
    global _bcrypt_semaphore, _bcrypt_semaphore_key
    loop_id = id(asyncio.get_running_loop())
    key = (loop_id, max_concurrency)
    if _bcrypt_semaphore is None or _bcrypt_semaphore_key != key:
        _bcrypt_semaphore = asyncio.Semaphore(max_concurrency)
        _bcrypt_semaphore_key = key
    return _bcrypt_semaphore


def validate_password_utf8_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise ValueError("La contraseña debe ser una cadena de texto.")
    encoded = password.encode("utf-8")
    if len(encoded) < 1:
        raise ValueError("La contraseña no puede estar vacía.")
    if len(encoded) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(
            f"La contraseña no puede superar los {MAX_BCRYPT_PASSWORD_BYTES} bytes en UTF-8."
        )
    return encoded


def _hash_password_sync(password_bytes: bytes, rounds: int) -> str:
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def _verify_password_sync(password_bytes: bytes, hashed_bytes: bytes) -> bool:
    return bcrypt.checkpw(password_bytes, hashed_bytes)


async def hash_password(password: str, settings: Settings | None = None) -> str:
    password_bytes = validate_password_utf8_bytes(password)
    cfg = settings or get_settings()
    sem = _get_bcrypt_semaphore(cfg.BCRYPT_MAX_CONCURRENCY)
    async with sem:
        return await asyncio.to_thread(_hash_password_sync, password_bytes, cfg.BCRYPT_ROUNDS)


async def verify_password(
    plain_password: str,
    hashed_password: str,
    settings: Settings | None = None,
) -> bool:
    password_bytes = validate_password_utf8_bytes(plain_password)
    hashed_bytes = hashed_password.encode("utf-8")
    cfg = settings or get_settings()
    sem = _get_bcrypt_semaphore(cfg.BCRYPT_MAX_CONCURRENCY)
    async with sem:
        return await asyncio.to_thread(_verify_password_sync, password_bytes, hashed_bytes)


async def get_dummy_hash(
    request: Request | None = None,
    settings: Settings | None = None,
) -> str:
    global _cached_dummy_hash
    if request is not None:
        state_dummy = getattr(getattr(request, "app", None), "state", None)
        dummy_val = getattr(state_dummy, "dummy_hash", None)
        if isinstance(dummy_val, str) and dummy_val.startswith("$2"):
            return dummy_val

    if _cached_dummy_hash is None:
        _cached_dummy_hash = await hash_password("dummy_password", settings=settings)
    return _cached_dummy_hash


def create_access_token(
    usuario_id: int,
    roles: Sequence[str] | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
    iat_timestamp: float | None = None,
) -> str:
    cfg = settings or get_settings()
    now_dt = now or datetime.now(timezone.utc)
    iat_val = float(iat_timestamp) if iat_timestamp is not None else float(now_dt.timestamp())
    exp_val = float(iat_val + cfg.JWT_EXPIRATION_SECONDS)
    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "iat": iat_val,
        "exp": exp_val,
        "roles": [str(r) for r in (roles or [])],
    }
    return jwt.encode(payload, cfg.JWT_SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    decoded = jwt.decode(
        token,
        cfg.JWT_SECRET_KEY,
        algorithms=[cfg.JWT_ALGORITHM],
    )
    return dict(decoded)


def set_auth_cookie(
    response: Response,
    token: str,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        max_age=cfg.JWT_EXPIRATION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=cfg.COOKIE_SECURE,
        path="/",
    )


def clear_auth_cookie(
    response: Response,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        httponly=True,
        samesite="lax",
        secure=cfg.COOKIE_SECURE,
        path="/",
    )

