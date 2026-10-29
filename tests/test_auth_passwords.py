import asyncio
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from app.core.config import Settings
import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401


@pytest.mark.asyncio
async def test_security_hash_verify_and_dummy_hash_happy_path() -> None:
    from app.core.security import get_dummy_hash, hash_password, verify_password

    # Arrange
    plain = "ClaveSegura123!"

    # Act
    hashed = await hash_password(plain)
    is_valid = await verify_password(plain, hashed)
    is_invalid = await verify_password("OtraClave", hashed)
    dummy = await get_dummy_hash()

    # Assert
    assert hashed.startswith("$2b$")
    assert is_valid is True
    assert is_invalid is False
    assert dummy.startswith("$2b$")
    assert await verify_password(plain, dummy) is False


@pytest.mark.asyncio
async def test_security_password_utf8_72_bytes_boundary_and_multibyte_rejection() -> None:
    from app.core.security import hash_password, verify_password

    # Arrange: 72 bytes exactos en ASCII y en multibyte ('ñ' = 2 bytes en UTF-8)
    exact_72_ascii = "a" * 72
    exact_72_utf8_multibyte = "ñ" * 36  # 36 chars == 72 bytes UTF-8
    over_73_ascii = "a" * 73
    over_80_utf8_multibyte = "ñ" * 40  # 40 chars == 80 bytes UTF-8 (> 72 bytes)

    # Act & Assert: 72 bytes exactos funcionan
    hash_ascii = await hash_password(exact_72_ascii)
    assert await verify_password(exact_72_ascii, hash_ascii) is True

    hash_multi = await hash_password(exact_72_utf8_multibyte)
    assert await verify_password(exact_72_utf8_multibyte, hash_multi) is True

    # Act & Assert: vacio, 73 bytes ASCII y 40 'ñ' (80 bytes UTF-8) lanzan ValueError
    with pytest.raises(ValueError):
        await hash_password("")

    with pytest.raises(ValueError):
        await hash_password(over_73_ascii)

    with pytest.raises(ValueError):
        await hash_password(over_80_utf8_multibyte)

    with pytest.raises(ValueError):
        await verify_password(over_73_ascii, hash_ascii)

    with pytest.raises(ValueError):
        await verify_password(over_80_utf8_multibyte, hash_multi)


@pytest.mark.asyncio
async def test_security_bcrypt_uses_to_thread_and_semaphore_concurrency_limit() -> None:
    from app.core import security
    from app.core.security import get_dummy_hash, hash_password

    # Arrange: configuracion con BCRYPT_MAX_CONCURRENCY=2 y BCRYPT_ROUNDS=4
    custom_settings = Settings(
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_DB="d",
        JWT_SECRET_KEY="s",
        BCRYPT_ROUNDS=4,
        BCRYPT_MAX_CONCURRENCY=2,
        _env_file=None,
    )

    active = 0
    max_observed = 0
    orig_to_thread = asyncio.to_thread

    async def tracked_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal active, max_observed
        active += 1
        max_observed = max(max_observed, active)
        await asyncio.sleep(0.02)
        try:
            return await orig_to_thread(func, *args, **kwargs)
        finally:
            active -= 1

    # Act: lanzar 5 hashes concurrentes bajo semaforo de capacidad 2
    with patch.object(security.asyncio, "to_thread", side_effect=tracked_to_thread):
        results = await asyncio.gather(
            *[hash_password(f"pass_{i}", settings=custom_settings) for i in range(5)]
        )

    # Assert: todas las llamadas pasaron por to_thread y nunca superaron concurrencia 2
    assert len(results) == 5
    assert 1 <= max_observed <= 2

    # Verificar que get_dummy_hash lee request.app.state.dummy_hash cuando existe
    fake_request = MagicMock()
    fake_request.app.state.dummy_hash = "$2b$12$abcdefghijklmnopqrstuv1234567890123456789012345678901"
    assert await get_dummy_hash(fake_request) == fake_request.app.state.dummy_hash


def test_security_jwt_microsecond_iat_and_auth_cookies_happy_path() -> None:
    from datetime import datetime, timezone
    from fastapi import Response
    from app.core.security import (
        clear_auth_cookie,
        create_access_token,
        decode_access_token,
        set_auth_cookie,
    )

    # Arrange
    now_dt = datetime.now(timezone.utc).replace(microsecond=654321)

    # Act
    token = create_access_token(usuario_id=42, roles=["CLIENTE"], now=now_dt)
    payload = decode_access_token(token)

    resp_set = Response()
    set_auth_cookie(resp_set, token)
    set_cookie_header = resp_set.headers.get("set-cookie", "")

    resp_clear = Response()
    clear_auth_cookie(resp_clear)
    clear_cookie_header = resp_clear.headers.get("set-cookie", "")

    # Assert
    assert payload["sub"] == "42"
    assert isinstance(payload["iat"], float)
    assert payload["iat"] == now_dt.timestamp()
    assert payload["iat"] % 1 != 0  # Con fraccion de microsegundos, nunca truncado a int
    assert payload["roles"] == ["CLIENTE"]

    assert "access_token=" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "SameSite=lax" in set_cookie_header or "SameSite=Lax" in set_cookie_header
    assert "Max-Age=1800" in set_cookie_header
    assert "Path=/" in set_cookie_header

    assert "access_token=" in clear_cookie_header
    assert "Max-Age=0" in clear_cookie_header


def test_security_jwt_custom_settings_secure_cookie_and_invalid_tokens() -> None:
    from datetime import datetime, timedelta, timezone
    from fastapi import Response
    import jwt
    from app.core.security import (
        create_access_token,
        decode_access_token,
        set_auth_cookie,
    )

    # Arrange
    secure_settings = Settings(
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_DB="d",
        JWT_SECRET_KEY="custom_secret_key_with_at_least_32_bytes_length_123",
        JWT_EXPIRATION_SECONDS=900,
        COOKIE_SECURE=True,
        _env_file=None,
    )
    other_settings = Settings(
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_DB="d",
        JWT_SECRET_KEY="wrong_secret_key_with_at_least_32_bytes_length_456",
        _env_file=None,
    )

    # Act & Assert: iat_timestamp explicito con microsegundos y cookie Secure
    explicit_iat = datetime.now(timezone.utc).timestamp() + 0.123456
    token = create_access_token(
        usuario_id=99,
        roles=["ADMIN", "RECEPCION"],
        settings=secure_settings,
        iat_timestamp=explicit_iat,
    )
    decoded = decode_access_token(token, settings=secure_settings)
    assert decoded["sub"] == "99"
    assert decoded["iat"] == explicit_iat
    assert decoded["exp"] == explicit_iat + 900
    assert decoded["roles"] == ["ADMIN", "RECEPCION"]

    resp = Response()
    set_auth_cookie(resp, token, settings=secure_settings)
    cookie_hdr = resp.headers.get("set-cookie", "")
    assert "Secure" in cookie_hdr
    assert "Max-Age=900" in cookie_hdr

    # Firma invalida lanza PyJWTError
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token, settings=other_settings)

    # Token expirado lanza ExpiredSignatureError
    past_dt = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_token = create_access_token(usuario_id=99, settings=secure_settings, now=past_dt)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token, settings=secure_settings)


def test_usuarios_schemas_happy_path_and_serialization() -> None:
    from app.modules.usuarios.models import Usuario
    from app.modules.usuarios.schemas import (
        CambiarPasswordRequest,
        LoginRequest,
        LoginResponse,
        RegistroClienteRequest,
        UsuarioResponse,
    )

    # Arrange & Act
    reg = RegistroClienteRequest(
        email="cliente@taller.com",
        password="MiPassword72",
        nombre="Laura Cliente",
        documento="33444555",
        telefono="1122334455",
    )
    login = LoginRequest(email="cliente@taller.com", password="MiPassword72")
    cambio = CambiarPasswordRequest(
        password_actual="MiPassword72",
        password_nueva="NuevaPassword72",
    )
    login_resp = LoginResponse(
        mensaje="Sesión iniciada",
        debe_cambiar_password=False,
        expira_en_segundos=1800,
    )

    orm_user = Usuario(
        id=7,
        email="cliente@taller.com",
        nombre="Laura Cliente",
        password_hash="secret_hash_never_exposed",
        activo=True,
        debe_cambiar_password=False,
    )
    user_resp = UsuarioResponse(
        id=orm_user.id,  # type: ignore[arg-type]
        email=orm_user.email,
        nombre=orm_user.nombre,
        activo=orm_user.activo,
        debe_cambiar_password=orm_user.debe_cambiar_password,
        roles=["CLIENTE"],
        roles_token=["CLIENTE"],
    )

    # Assert
    assert reg.email == "cliente@taller.com"
    assert login.email == "cliente@taller.com"
    assert cambio.password_nueva == "NuevaPassword72"
    assert login_resp.expira_en_segundos == 1800
    dumped = user_resp.model_dump()
    assert "password_hash" not in dumped
    assert dumped["roles"] == ["CLIENTE"]
    assert dumped["roles_token"] == ["CLIENTE"]


def test_usuarios_schemas_extra_forbid_and_password_utf8_72_bytes_validation() -> None:
    from app.modules.usuarios.schemas import (
        CambiarPasswordRequest,
        LoginRequest,
        RegistroClienteRequest,
    )

    over_73_ascii = "x" * 73
    over_40_multibyte = "ñ" * 40  # 80 bytes UTF-8

    # 1. Rechazo por campos extra no declarados (Regla Dura #1: extra="forbid")
    with pytest.raises(ValidationError):
        RegistroClienteRequest(
            email="a@b.com",
            password="ClaveValida1",
            nombre="Juan",
            documento="123",
            telefono="456",
            rol="ADMIN",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        LoginRequest(
            email="a@b.com",
            password="ClaveValida1",
            remember_me=True,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        CambiarPasswordRequest(
            password_actual="ClaveValida1",
            password_nueva="ClaveValida2",
            forzar=True,  # type: ignore[call-arg]
        )

    # 2. Rechazo por contraseñas de 73 bytes ASCII o 40 caracteres 'ñ' (80 bytes UTF-8)
    for invalid_pwd in ("", over_73_ascii, over_40_multibyte):
        with pytest.raises(ValidationError):
            RegistroClienteRequest(
                email="a@b.com",
                password=invalid_pwd,
                nombre="Juan",
                documento="123",
                telefono="456",
            )

        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com", password=invalid_pwd)

        with pytest.raises(ValidationError):
            CambiarPasswordRequest(password_actual=invalid_pwd, password_nueva="ClaveValida2")

        with pytest.raises(ValidationError):
            CambiarPasswordRequest(password_actual="ClaveValida1", password_nueva=invalid_pwd)


@pytest.mark.asyncio
async def test_usuarios_repositories_and_uow_integration_rn08() -> None:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.core.unit_of_work import UnitOfWork
    from app.modules.usuarios.models import (
        AsignacionRol,
        EventoSeguridad,
        IntentoAcceso,
        RolEnum,
        Usuario,
    )
    from app.modules.usuarios.repository import (
        AsignacionRolRepository,
        EventoSeguridadRepository,
        IntentoAccesoRepository,
        UsuarioRepository,
    )
    from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # 1. Verificar registro de repositorios en UnitOfWork y UsuariosUnitOfWork
            uow = UsuariosUnitOfWork(session)
            assert isinstance(uow, UnitOfWork)
            async with uow as active_uow:
                assert isinstance(active_uow.usuarios, UsuarioRepository)
                assert isinstance(active_uow.asignaciones_rol, AsignacionRolRepository)
                assert isinstance(active_uow.intentos_acceso, IntentoAccesoRepository)
                assert isinstance(active_uow.eventos_seguridad, EventoSeguridadRepository)
                assert hasattr(active_uow, "clientes")
                assert hasattr(active_uow, "vehiculos")

            user_repo = UsuarioRepository(session)
            rol_repo = AsignacionRolRepository(session)
            intento_repo = IntentoAccesoRepository(session)
            evento_repo = EventoSeguridadRepository(session)

            # 2. UsuarioRepository.get_by_email y flush sin commit
            user = await user_repo.add(
                Usuario(
                    email="repo_usr@taller.com",
                    nombre="Usuario Repo",
                    password_hash="hash_repo",
                )
            )
            assert user.id is not None
            found_usr = await user_repo.get_by_email("repo_usr@taller.com")
            assert found_usr is not None and found_usr.id == user.id
            assert await user_repo.get_by_email("inexistente@taller.com") is None

            # 3. AsignacionRolRepository.get_active_roles_by_usuario_id (vigentes vs revocados vs vencidos)
            now = datetime.now(timezone.utc)
            await rol_repo.add(
                AsignacionRol(
                    usuario_id=user.id,
                    rol=RolEnum.CLIENTE,
                    desde=now - timedelta(days=5),
                )
            )
            await rol_repo.add(
                AsignacionRol(
                    usuario_id=user.id,
                    rol=RolEnum.MECANICO,
                    desde=now - timedelta(days=5),
                    vence_en=now + timedelta(days=1),
                )
            )
            await rol_repo.add(
                AsignacionRol(
                    usuario_id=user.id,
                    rol=RolEnum.RECEPCION,
                    desde=now - timedelta(days=5),
                    vence_en=now - timedelta(seconds=10),  # Vencido
                )
            )
            await rol_repo.add(
                AsignacionRol(
                    usuario_id=user.id,
                    rol=RolEnum.ADMIN,
                    desde=now - timedelta(days=5),
                    revocada_en=now - timedelta(minutes=1),  # Revocado
                )
            )

            active_roles = await rol_repo.get_active_roles_by_usuario_id(user.id, now=now)
            assert set(active_roles) == {"CLIENTE", "MECANICO"}

            # 4. IntentoAccesoRepository.count_consecutive_failures_in_window (RN-08)
            email_test = "ratelimit_repo@taller.com"
            ip_test = "10.0.0.55"

            # Un fallo hace 90 segundos (fuera de la ventana de 60s) no cuenta
            await intento_repo.add(
                IntentoAcceso(
                    email=email_test,
                    ip=ip_test,
                    exito=False,
                    cuando=now - timedelta(seconds=90),
                )
            )
            # 3 fallos dentro de la ventana (hace 40s, 30s, 20s)
            for sec in (40, 30, 20):
                await intento_repo.add(
                    IntentoAcceso(
                        email=email_test,
                        ip=ip_test,
                        exito=False,
                        cuando=now - timedelta(seconds=sec),
                    )
                )

            assert (
                await intento_repo.count_consecutive_failures_in_window(
                    email_test, ip_test, window_seconds=60, now=now
                )
                == 3
            )

            # Un login exitoso hace 10s reinicia la cuenta sin borrar filas previas (RN-08)
            await intento_repo.add(
                IntentoAcceso(
                    email=email_test,
                    ip=ip_test,
                    exito=True,
                    cuando=now - timedelta(seconds=10),
                )
            )
            assert (
                await intento_repo.count_consecutive_failures_in_window(
                    email_test, ip_test, window_seconds=60, now=now
                )
                == 0
            )

            # Un nuevo fallo hace 5s cuenta como 1 (y las 6 filas historicas siguen en la tabla)
            await intento_repo.add(
                IntentoAcceso(
                    email=email_test,
                    ip=ip_test,
                    exito=False,
                    cuando=now - timedelta(seconds=5),
                )
            )
            assert (
                await intento_repo.count_consecutive_failures_in_window(
                    email_test, ip_test, window_seconds=60, now=now
                )
                == 1
            )

            # 5. EventoSeguridadRepository
            ev = await evento_repo.add(
                EventoSeguridad(
                    actor="repo_usr@taller.com",
                    accion="Prueba repo",
                    cuando=now,
                )
            )
            assert ev.id is not None

            # Rollback demuestra que ningun repositorio hizo commit() por su cuenta (Regla Dura #3)
            await session.rollback()

        async with session_factory() as clean_session:
            clean_repo = UsuarioRepository(clean_session)
            assert await clean_repo.get_by_email("repo_usr@taller.com") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_usuarios_repositories_ip_email_isolation_and_uow_rollback() -> None:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente
    from app.modules.usuarios.models import (
        AsignacionRol,
        EventoSeguridad,
        IntentoAcceso,
        RolEnum,
        Usuario,
    )
    from app.modules.usuarios.repository import IntentoAccesoRepository
    from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                now = datetime.now(timezone.utc)
                intento_repo = IntentoAccesoRepository(session)

                # Aislamiento por (email, ip): fallos desde otra IP u otro email no suman al par consultado
                await intento_repo.add(
                    IntentoAcceso(email="u1@taller.com", ip="1.1.1.1", exito=False, cuando=now - timedelta(seconds=5))
                )
                await intento_repo.add(
                    IntentoAcceso(email="u1@taller.com", ip="2.2.2.2", exito=False, cuando=now - timedelta(seconds=5))
                )
                await intento_repo.add(
                    IntentoAcceso(email="u2@taller.com", ip="1.1.1.1", exito=False, cuando=now - timedelta(seconds=5))
                )

                assert (
                    await intento_repo.count_consecutive_failures_in_window(
                        "u1@taller.com", "1.1.1.1", window_seconds=60, now=now
                    )
                    == 1
                )

                # Reversion atomica multi-entidad en UsuariosUnitOfWork ante excepcion
                uow = UsuariosUnitOfWork(session)
                with pytest.raises(RuntimeError):
                    async with uow:
                        u = await uow.usuarios.add(
                            Usuario(email="rollback_uow@taller.com", nombre="Rollback", password_hash="h")
                        )
                        assert u.id is not None
                        await uow.asignaciones_rol.add(
                            AsignacionRol(usuario_id=u.id, rol=RolEnum.CLIENTE)
                        )
                        await uow.clientes.add(
                            Cliente(usuario_id=u.id, nombre="Rollback", documento="DOC-RB-99", telefono="123")
                        )
                        await uow.eventos_seguridad.add(
                            EventoSeguridad(actor=u.email, accion="Intento fallido")
                        )
                        raise RuntimeError("Fallo simulado dentro del UoW")

                assert await uow.usuarios.get_by_email("rollback_uow@taller.com") is None
                assert await uow.clientes.get_by_documento("DOC-RB-99") is None
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_registro_c03_atomic_creation_and_rn02_rollback() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.modules.clientes.models import Cliente
    from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
    from main import app

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                # Arrange: cliente previo dado de alta en recepcion sin usuario web (RN-02)
                cliente_mostrador = Cliente(
                    usuario_id=None,
                    nombre="Cliente Mostrador",
                    documento="DOC-MOSTRADOR-001",
                    telefono="1144445555",
                )
                session.add(cliente_mostrador)
                await session.commit()
                assert cliente_mostrador.id is not None
                mostrador_id = cliente_mostrador.id

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                app.dependency_overrides[get_session] = _override_session

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 1. Caso C-03 feliz: POST /auth/registro -> 201 Created
                    res_201 = await client.post(
                        "/auth/registro",
                        json={
                            "email": "nuevo_cliente@taller.com",
                            "password": "ClaveCliente123!",
                            "nombre": "Martín Web",
                            "documento": "DOC-WEB-001",
                            "telefono": "1166667777",
                        },
                    )
                    assert res_201.status_code == 201
                    body_201 = res_201.json()
                    assert body_201["email"] == "nuevo_cliente@taller.com"
                    assert body_201["nombre"] == "Martín Web"
                    assert body_201["activo"] is True
                    assert body_201["debe_cambiar_password"] is False
                    assert body_201["roles"] == ["CLIENTE"]
                    assert "password_hash" not in body_201
                    user_id = body_201["id"]

                    # Verificar que se persistieron Usuario, AsignacionRol, Cliente y EventoSeguridad
                    db_cli = (
                        await session.execute(
                            select(Cliente).where(Cliente.documento == "DOC-WEB-001")
                        )
                    ).scalars().first()
                    assert db_cli is not None and db_cli.usuario_id == user_id

                    db_rol = (
                        await session.execute(
                            select(AsignacionRol).where(AsignacionRol.usuario_id == user_id)
                        )
                    ).scalars().all()
                    assert [r.rol for r in db_rol] == ["CLIENTE"]

                    db_ev = (
                        await session.execute(
                            select(EventoSeguridad).where(
                                EventoSeguridad.actor == "nuevo_cliente@taller.com"
                            )
                        )
                    ).scalars().first()
                    assert db_ev is not None

                    # 2. Caso C-03 / RN-02: documento ya existe en cliente de mostrador -> 409 y rollback total
                    res_409_doc = await client.post(
                        "/auth/registro",
                        json={
                            "email": "intruso_doc@taller.com",
                            "password": "ClaveCliente123!",
                            "nombre": "Intruso Documento",
                            "documento": "DOC-MOSTRADOR-001",
                            "telefono": "1199990000",
                        },
                    )
                    assert res_409_doc.status_code == 409

                    # Confirmar que NO quedo fila huerfana en usuario ni se vinculo el cliente existente
                    session.expire_all()
                    orphan_user = (
                        await session.execute(
                            select(Usuario).where(Usuario.email == "intruso_doc@taller.com")
                        )
                    ).scalars().first()
                    assert orphan_user is None

                    mostrador_check = await session.get(Cliente, mostrador_id)
                    assert mostrador_check is not None
                    assert mostrador_check.usuario_id is None
                    assert mostrador_check.nombre == "Cliente Mostrador"

                    # 3. Conflicto por email ya registrado -> 409 Conflict
                    res_409_email = await client.post(
                        "/auth/registro",
                        json={
                            "email": "nuevo_cliente@taller.com",
                            "password": "OtraClave123!",
                            "nombre": "Otro Nombre",
                            "documento": "DOC-LIBRE-999",
                            "telefono": "1100000000",
                        },
                    )
                    assert res_409_email.status_code == 409

                    # 4. Contraseña > 72 bytes UTF-8 (73 ASCII y 40 'ñ') -> 422 sin error 500
                    res_422_ascii = await client.post(
                        "/auth/registro",
                        json={
                            "email": "long1@taller.com",
                            "password": "a" * 73,
                            "nombre": "Long ASCII",
                            "documento": "DOC-LONG-1",
                            "telefono": "1100001111",
                        },
                    )
                    assert res_422_ascii.status_code == 422

                    res_422_utf8 = await client.post(
                        "/auth/registro",
                        json={
                            "email": "long2@taller.com",
                            "password": "ñ" * 40,
                            "nombre": "Long UTF8",
                            "documento": "DOC-LONG-2",
                            "telefono": "1100002222",
                        },
                    )
                    assert res_422_utf8.status_code == 422
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_login_logout_c04_c05_c06_rn08_rn09() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.security import decode_access_token, hash_password
    from app.modules.usuarios import service as usuarios_service_mod
    from app.modules.usuarios.models import AsignacionRol, IntentoAcceso, RolEnum, Usuario
    from main import app

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                pwd_hash = await hash_password("SecretaLogin1!")
                user = Usuario(
                    email="login_ok@taller.com",
                    nombre="Usuario Login",
                    password_hash=pwd_hash,
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add(user)
                await session.flush()
                assert user.id is not None
                session.add(AsignacionRol(usuario_id=user.id, rol=RolEnum.CLIENTE))
                await session.commit()

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                app.dependency_overrides[get_session] = _override_session

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 1. Caso C-04: Login exitoso -> 200 OK, cookie HttpOnly access_token, sin JWT en body
                    res_ok = await client.post(
                        "/auth/login",
                        json={"email": "login_ok@taller.com", "password": "SecretaLogin1!"},
                    )
                    assert res_ok.status_code == 200
                    body_ok = res_ok.json()
                    assert body_ok == {
                        "mensaje": "Sesión iniciada",
                        "debe_cambiar_password": False,
                        "expira_en_segundos": settings.JWT_EXPIRATION_SECONDS,
                    }
                    assert "access_token" not in body_ok
                    assert "token" not in body_ok

                    set_cookie_hdr = res_ok.headers.get("set-cookie", "")
                    assert "access_token=" in set_cookie_hdr
                    assert "HttpOnly" in set_cookie_hdr
                    assert "SameSite=lax" in set_cookie_hdr or "SameSite=Lax" in set_cookie_hdr

                    cookie_jwt = res_ok.cookies.get("access_token")
                    assert cookie_jwt is not None
                    decoded = decode_access_token(cookie_jwt)
                    assert decoded["sub"] == str(user.id)
                    assert isinstance(decoded["iat"], float)
                    assert decoded["roles"] == ["CLIENTE"]

                    # Logout elimina la cookie access_token (Max-Age=0)
                    res_logout = await client.post("/auth/logout")
                    assert res_logout.status_code == 200
                    assert "Max-Age=0" in res_logout.headers.get("set-cookie", "")

                    # 2. Caso C-05 / RN-09: contraseña incorrecta vs correo inexistente
                    res_bad_pwd = await client.post(
                        "/auth/login",
                        json={"email": "login_ok@taller.com", "password": "ClaveIncorrecta"},
                    )
                    assert res_bad_pwd.status_code == 401
                    assert res_bad_pwd.json() == {"detail": "Credenciales inválidas."}

                    with patch.object(
                        usuarios_service_mod,
                        "verify_password",
                        wraps=usuarios_service_mod.verify_password,
                    ) as spy_verify:
                        res_no_email = await client.post(
                            "/auth/login",
                            json={"email": "no_existe_c05@taller.com", "password": "CualquierPassword"},
                        )
                        assert res_no_email.status_code == 401
                        assert res_no_email.json() == res_bad_pwd.json()
                        assert spy_verify.call_count == 1
                        called_plain, called_hash = spy_verify.call_args.args[:2]
                        assert called_plain == "CualquierPassword"
                        assert called_hash.startswith("$2")

                    # Verificar que ambos intentos fallidos quedaron persistidos en intento_acceso
                    session.expire_all()
                    intentos_no_email = (
                        await session.execute(
                            select(IntentoAcceso).where(
                                IntentoAcceso.email == "no_existe_c05@taller.com"
                            )
                        )
                    ).scalars().all()
                    assert len(intentos_no_email) == 1
                    assert intentos_no_email[0].exito is False

                    # 3. Caso C-06 / RN-08: 5 intentos fallidos consecutivos en 60s -> 6to devuelve 429 con Retry-After: 60 sin bcrypt
                    rate_email = "fuerzabruta_c06@taller.com"
                    for _ in range(5):
                        r_fail = await client.post(
                            "/auth/login",
                            json={"email": rate_email, "password": "WrongPassword"},
                        )
                        assert r_fail.status_code == 401

                    with patch.object(
                        usuarios_service_mod,
                        "verify_password",
                        wraps=usuarios_service_mod.verify_password,
                    ) as spy_verify_6th:
                        r_429 = await client.post(
                            "/auth/login",
                            json={"email": rate_email, "password": "WrongPassword"},
                        )
                        assert r_429.status_code == 429
                        assert r_429.headers.get("Retry-After") == "60"
                        assert spy_verify_6th.call_count == 0

                    session.expire_all()
                    intentos_rate = (
                        await session.execute(
                            select(IntentoAcceso).where(IntentoAcceso.email == rate_email)
                        )
                    ).scalars().all()
                    assert len(intentos_rate) == 5

                    # 4. Reinicio de la cuenta tras login exitoso sin borrar filas previas (RN-08)
                    # login_ok@taller.com ya tenia 1 exito + 1 fallo; sumamos 3 fallos mas (total 4 consecutivos)
                    for _ in range(3):
                        r_f = await client.post(
                            "/auth/login",
                            json={"email": "login_ok@taller.com", "password": "WrongPassword"},
                        )
                        assert r_f.status_code == 401

                    # Ahora un login exitoso reinicia la cuenta
                    r_reset_ok = await client.post(
                        "/auth/login",
                        json={"email": "login_ok@taller.com", "password": "SecretaLogin1!"},
                    )
                    assert r_reset_ok.status_code == 200

                    # Si vuelve a fallar 2 veces mas, NO se bloquea con 429 (aunque en total historico haya 6 fallos)
                    for _ in range(2):
                        r_after = await client.post(
                            "/auth/login",
                            json={"email": "login_ok@taller.com", "password": "WrongPassword"},
                        )
                        assert r_after.status_code == 401

                    session.expire_all()
                    historial_login_ok = (
                        await session.execute(
                            select(IntentoAcceso).where(
                                IntentoAcceso.email == "login_ok@taller.com"
                            )
                        )
                    ).scalars().all()
                    # 1 exito inicial + 4 fallos + 1 exito reset + 2 fallos = 8 filas preservadas
                    assert len(historial_login_ok) == 8
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_yo_and_cambiar_password_c07_c08_rn06_rn07() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.security import hash_password
    from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, RolEnum, Usuario
    from main import app

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                provisoria_hash = await hash_password("Provisoria123!")
                user = Usuario(
                    email="provisorio_c07@taller.com",
                    nombre="Empleado Provisorio",
                    password_hash=provisoria_hash,
                    activo=True,
                    debe_cambiar_password=True,
                )
                session.add(user)
                await session.flush()
                assert user.id is not None
                user_id = user.id

                rol_cli = AsignacionRol(usuario_id=user_id, rol=RolEnum.CLIENTE)
                session.add(rol_cli)
                await session.commit()

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                app.dependency_overrides[get_session] = _override_session

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 1. Login con debe_cambiar_password=True -> 200 OK
                    res_login = await client.post(
                        "/auth/login",
                        json={"email": "provisorio_c07@taller.com", "password": "Provisoria123!"},
                    )
                    assert res_login.status_code == 200
                    assert res_login.json()["debe_cambiar_password"] is True
                    old_token = res_login.cookies.get("access_token")
                    assert old_token is not None

                    # 2. Caso C-07 / RN-06: ruta del grupo protegido rechaza con 403 mientras debe_cambiar_password=True
                    res_protected_403 = await client.get("/mis-vehiculos")
                    assert res_protected_403.status_code == 403

                    # 3. GET /auth/yo en grupo abierto SI permite acceso con debe_cambiar_password=True
                    # Si ademas agregamos un rol en DB despues de emitido el token, /auth/yo muestra roles != roles_token
                    session.add(AsignacionRol(usuario_id=user_id, rol=RolEnum.MECANICO))
                    await session.commit()

                    res_yo = await client.get("/auth/yo")
                    assert res_yo.status_code == 200
                    body_yo = res_yo.json()
                    assert body_yo["id"] == user_id
                    assert body_yo["email"] == "provisorio_c07@taller.com"
                    assert body_yo["debe_cambiar_password"] is True
                    assert "password_hash" not in body_yo
                    assert set(body_yo["roles"]) == {"CLIENTE", "MECANICO"}
                    assert body_yo["roles_token"] == ["CLIENTE"]

                    # 4. Regla Dura #5: GET /auth/yo sin cookie pero con Authorization: Bearer -> 401
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as bearer_client:
                        res_bearer_401 = await bearer_client.get(
                            "/auth/yo",
                            headers={"Authorization": f"Bearer {old_token}"},
                        )
                        assert res_bearer_401.status_code == 401

                    # 5. Cambio de contraseña con password_actual incorrecta -> 401 y no invalida sesion actual
                    res_bad_actual = await client.post(
                        "/auth/cambiar-password",
                        json={
                            "password_actual": "Incorrecta999!",
                            "password_nueva": "Definitiva456!",
                        },
                    )
                    assert res_bad_actual.status_code == 401

                    # 6. Caso C-08 / RN-07: cambio de contraseña inmediato (sin sleep)
                    res_cambio = await client.post(
                        "/auth/cambiar-password",
                        json={
                            "password_actual": "Provisoria123!",
                            "password_nueva": "Definitiva456!",
                        },
                    )
                    assert res_cambio.status_code == 200
                    body_cambio = res_cambio.json()
                    assert body_cambio["debe_cambiar_password"] is False
                    new_token = res_cambio.cookies.get("access_token")
                    assert new_token is not None
                    assert new_token != old_token

                    # Verificar que la nueva cookie funciona en /auth/yo y ahora tambien en /mis-vehiculos (200 OK)
                    res_yo_after = await client.get("/auth/yo")
                    assert res_yo_after.status_code == 200
                    assert res_yo_after.json()["debe_cambiar_password"] is False

                    res_protected_200 = await client.get("/mis-vehiculos")
                    assert res_protected_200.status_code == 200

                    # Verificar que la cookie ANTERIOR (old_token) queda invalidada en el acto con 401 (RN-07)
                    async with httpx.AsyncClient(
                        transport=transport,
                        base_url="http://test",
                        cookies={"access_token": old_token},
                    ) as old_session_client:
                        res_old_cookie = await old_session_client.get("/auth/yo")
                        assert res_old_cookie.status_code == 401

                    # Verificar actualizacion de password_cambiada_en y EventoSeguridad en DB
                    session.expire_all()
                    db_user = await session.get(Usuario, user_id)
                    assert db_user is not None
                    assert db_user.debe_cambiar_password is False
                    assert db_user.password_cambiada_en is not None
                    assert db_user.password_cambiada_en.tzinfo is not None

                    ev_cambio = (
                        await session.execute(
                            select(EventoSeguridad).where(
                                EventoSeguridad.actor == "provisorio_c07@taller.com"
                            )
                        )
                    ).scalars().first()
                    assert ev_cambio is not None
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()










