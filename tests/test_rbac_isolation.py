import pytest
import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401


@pytest.mark.asyncio
async def test_dependencies_get_usuario_actual_alias_and_get_current_cliente_happy_path() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.dependencies import (
        get_current_cliente,
        get_current_user,
        get_usuario_actual,
    )
    from app.modules.clientes.models import Cliente
    from app.modules.usuarios.models import Usuario

    # Arrange
    assert get_usuario_actual is get_current_user

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
                user_with_cli = Usuario(
                    email="cli_dep_1@taller.com",
                    nombre="Cliente Con Ficha",
                    password_hash="hash_1",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add(user_with_cli)
                await session.flush()
                assert user_with_cli.id is not None

                ficha = Cliente(
                    usuario_id=user_with_cli.id,
                    nombre="Cliente Con Ficha",
                    documento="DOC-DEP-001",
                    telefono="1122334455",
                )
                session.add(ficha)
                await session.flush()
                assert ficha.id is not None

                # Act
                resolved = await get_current_cliente(
                    current_user=user_with_cli,
                    session=session,
                )

                # Assert
                assert resolved is not None
                assert resolved.id == ficha.id
                assert resolved.usuario_id == user_with_cli.id
                assert resolved.documento == "DOC-DEP-001"
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dependencies_get_current_cliente_none_and_router_protegido_rn06_enforcement() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.dependencies import (
        get_current_active_user,
        get_current_cliente,
    )
    from app.modules.usuarios.models import Usuario
    from main import router_protegido

    # Arrange: verify router_protegido carries get_current_active_user dependency
    dep_callables = [d.dependency for d in router_protegido.dependencies]
    assert get_current_active_user in dep_callables

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
                staff_user = Usuario(
                    email="staff_sin_ficha@taller.com",
                    nombre="Staff Sin Ficha",
                    password_hash="hash_staff",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add(staff_user)
                await session.flush()
                assert staff_user.id is not None

                unpersisted_user = Usuario(
                    id=None,
                    email="unpersisted@taller.com",
                    nombre="Unpersisted",
                    password_hash="h",
                )

                # Act
                res_staff = await get_current_cliente(current_user=staff_user, session=session)
                res_unpersisted = await get_current_cliente(current_user=unpersisted_user, session=session)

                # Assert
                assert res_staff is None
                assert res_unpersisted is None
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


def test_rbac_schemas_happy_path_and_from_attributes() -> None:
    from datetime import datetime, timedelta, timezone
    from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, RolEnum
    from app.modules.usuarios.schemas import (
        AsignacionRolResponse,
        AsignarRolRequest,
        CrearUsuarioRequest,
        EventoSeguridadResponse,
    )

    # Arrange
    now_utc = datetime.now(timezone.utc)
    future_utc = now_utc + timedelta(days=30)

    # Act
    crear_req = CrearUsuarioRequest(
        email="  mecanico1@taller.com  ",
        nombre="  Pedro Mecánico  ",
        password="ClaveProvisoria123!",
    )
    asignar_sin_venc = AsignarRolRequest(rol=RolEnum.MECANICO)
    asignar_con_venc = AsignarRolRequest(rol=RolEnum.RECEPCION, vence_en=future_utc)

    orm_asig = AsignacionRol(
        id=15,
        usuario_id=4,
        rol=RolEnum.MECANICO,
        desde=now_utc,
        vence_en=future_utc,
        revocada_en=None,
        otorgada_por=1,
    )
    asig_resp = AsignacionRolResponse.model_validate(orm_asig)

    orm_ev = EventoSeguridad(
        id=22,
        cuando=now_utc,
        actor="admin@taller.com",
        accion="Asignación de rol MECANICO a mecanico1@taller.com",
    )
    ev_resp = EventoSeguridadResponse.model_validate(orm_ev)

    # Assert
    assert crear_req.email == "mecanico1@taller.com"
    assert crear_req.nombre == "Pedro Mecánico"
    assert crear_req.password == "ClaveProvisoria123!"
    assert asignar_sin_venc.rol == RolEnum.MECANICO
    assert asignar_sin_venc.vence_en is None
    assert asignar_con_venc.rol == RolEnum.RECEPCION
    assert asignar_con_venc.vence_en == future_utc

    assert asig_resp.id == 15
    assert asig_resp.usuario_id == 4
    assert asig_resp.rol == "MECANICO"
    assert asig_resp.vence_en == future_utc
    assert asig_resp.revocada_en is None
    assert asig_resp.otorgada_por == 1

    assert ev_resp.id == 22
    assert ev_resp.actor == "admin@taller.com"
    assert ev_resp.accion == "Asignación de rol MECANICO a mecanico1@taller.com"


def test_rbac_schemas_validation_errors_extra_forbid_password_bytes_and_vence_en() -> None:
    from datetime import datetime, timedelta, timezone
    from pydantic import ValidationError
    from app.modules.usuarios.models import RolEnum
    from app.modules.usuarios.schemas import AsignarRolRequest, CrearUsuarioRequest

    # 1. CrearUsuarioRequest: 72 bytes exactos (ASCII y multibyte) pasan
    ok_ascii_72 = CrearUsuarioRequest(
        email="ok72@taller.com",
        nombre="Empleado 72",
        password="a" * 72,
    )
    ok_multi_72 = CrearUsuarioRequest(
        email="okmulti@taller.com",
        nombre="Empleado Multi",
        password="ñ" * 36,  # 72 bytes UTF-8
    )
    assert len(ok_ascii_72.password.encode("utf-8")) == 72
    assert len(ok_multi_72.password.encode("utf-8")) == 72

    # 2. CrearUsuarioRequest: rechazo de extra="forbid", vacíos y > 72 bytes UTF-8
    with pytest.raises(ValidationError):
        CrearUsuarioRequest(
            email="extra@taller.com",
            nombre="Extra",
            password="ClaveValida1!",
            rol="ADMIN",  # type: ignore[call-arg]
        )

    for blank in ("", "   "):
        with pytest.raises(ValidationError):
            CrearUsuarioRequest(email=blank, nombre="Valido", password="ClaveValida1!")
        with pytest.raises(ValidationError):
            CrearUsuarioRequest(email="ok@taller.com", nombre=blank, password="ClaveValida1!")

    for bad_pwd in ("", "a" * 73, "ñ" * 40):
        with pytest.raises(ValidationError):
            CrearUsuarioRequest(email="ok@taller.com", nombre="Valido", password=bad_pwd)

    # 3. AsignarRolRequest: rechazo de extra="forbid", rol inválido, vence_en naive y vence_en pasado
    with pytest.raises(ValidationError):
        AsignarRolRequest(
            rol=RolEnum.MECANICO,
            otorgada_por=1,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        AsignarRolRequest(rol="SUPERUSER")  # type: ignore[arg-type]

    # Fecha naive (sin zona horaria) -> ValidationError (422)
    with pytest.raises(ValidationError):
        AsignarRolRequest(
            rol=RolEnum.MECANICO,
            vence_en=datetime(2099, 12, 31, 23, 59, 59),
        )

    # Fecha en el pasado con timezone -> ValidationError (422)
    with pytest.raises(ValidationError):
        AsignarRolRequest(
            rol=RolEnum.MECANICO,
            vence_en=datetime.now(timezone.utc) - timedelta(seconds=5),
        )

    # 4. Fecha futura con offset -03:00 se normaliza a UTC
    tz_arg = timezone(timedelta(hours=-3))
    future_arg = datetime.now(tz_arg) + timedelta(days=7)
    req_tz = AsignarRolRequest(rol=RolEnum.RECEPCION, vence_en=future_arg)
    assert req_tz.vence_en is not None
    assert req_tz.vence_en.tzinfo == timezone.utc
    assert req_tz.vence_en == future_arg.astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_rbac_repositories_list_get_open_and_paginated_eventos() -> None:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, RolEnum, Usuario
    from app.modules.usuarios.repository import (
        AsignacionRolRepository,
        EventoSeguridadRepository,
        UsuarioRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            user_repo = UsuarioRepository(session)
            rol_repo = AsignacionRolRepository(session)
            ev_repo = EventoSeguridadRepository(session)

            now = datetime.now(timezone.utc)
            u1 = await user_repo.add(
                Usuario(
                    email="repo_rbac_u1@taller.com",
                    nombre="Usuario 1",
                    password_hash="h1",
                    activo=True,
                )
            )
            assert u1.id is not None

            # 1. Asignaciones: una revocada previa de MECANICO, una abierta vencida de MECANICO, una abierta vigente de RECEPCION
            a_rev = await rol_repo.add(
                AsignacionRol(
                    usuario_id=u1.id,
                    rol=RolEnum.MECANICO,
                    desde=now - timedelta(days=10),
                    revocada_en=now - timedelta(days=5),
                )
            )
            a_exp = await rol_repo.add(
                AsignacionRol(
                    usuario_id=u1.id,
                    rol=RolEnum.MECANICO,
                    desde=now - timedelta(days=4),
                    vence_en=now - timedelta(hours=1),
                    revocada_en=None,
                )
            )
            a_vig = await rol_repo.add(
                AsignacionRol(
                    usuario_id=u1.id,
                    rol=RolEnum.RECEPCION,
                    desde=now - timedelta(days=1),
                    vence_en=now + timedelta(days=5),
                    revocada_en=None,
                )
            )

            all_for_u1 = await rol_repo.list_by_usuario_id(u1.id)
            assert [a.id for a in all_for_u1] == [a_rev.id, a_exp.id, a_vig.id]

            open_mec = await rol_repo.get_open_by_usuario_and_rol(u1.id, "MECANICO")
            assert open_mec is not None and open_mec.id == a_exp.id

            open_rec = await rol_repo.get_open_by_usuario_and_rol(u1.id, "RECEPCION")
            assert open_rec is not None and open_rec.id == a_vig.id

            open_adm = await rol_repo.get_open_by_usuario_and_rol(u1.id, "ADMIN")
            assert open_adm is None

            # 2. EventoSeguridadRepository.list_paginated
            ev1 = await ev_repo.add(
                EventoSeguridad(
                    actor="admin@taller.com",
                    accion="Evento 1",
                    cuando=now - timedelta(minutes=2),
                )
            )
            ev2 = await ev_repo.add(
                EventoSeguridad(
                    actor="admin@taller.com",
                    accion="Evento 2",
                    cuando=now - timedelta(minutes=1),
                )
            )
            ev3 = await ev_repo.add(
                EventoSeguridad(
                    actor="admin@taller.com",
                    accion="Evento 3",
                    cuando=now,
                )
            )
            page_top2 = await ev_repo.list_paginated(offset=0, limit=2)
            assert len(page_top2) == 2
            assert page_top2[0].id == ev3.id
            assert page_top2[1].id == ev2.id

            # Rollback demuestra que los repositorios solo hicieron flush() y nunca commit()
            await session.rollback()

        async with session_factory() as verify_session:
            verify_user_repo = UsuarioRepository(verify_session)
            assert await verify_user_repo.get_by_email("repo_rbac_u1@taller.com") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rbac_repository_count_other_active_admins_excludes_revoked_expired_inactive_and_target() -> None:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.modules.usuarios.models import AsignacionRol, RolEnum, Usuario
    from app.modules.usuarios.repository import AsignacionRolRepository, UsuarioRepository

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
                user_repo = UsuarioRepository(session)
                rol_repo = AsignacionRolRepository(session)
                now = datetime.now(timezone.utc)

                # Limpiar asignaciones ADMIN previas que pudieran existir en el entorno para aislar el conteo
                from sqlalchemy import update
                await session.execute(
                    update(AsignacionRol)
                    .where(AsignacionRol.rol == RolEnum.ADMIN)
                    .where(AsignacionRol.revocada_en.is_(None))
                    .values(revocada_en=now - timedelta(days=1))
                )
                await session.flush()

                target_admin = await user_repo.add(
                    Usuario(email="adm_target@taller.com", nombre="Target", password_hash="h", activo=True)
                )
                revoked_admin = await user_repo.add(
                    Usuario(email="adm_revoked@taller.com", nombre="Revoked", password_hash="h", activo=True)
                )
                expired_admin = await user_repo.add(
                    Usuario(email="adm_expired@taller.com", nombre="Expired", password_hash="h", activo=True)
                )
                inactive_admin = await user_repo.add(
                    Usuario(email="adm_inactive@taller.com", nombre="Inactive", password_hash="h", activo=False)
                )
                recepcion_only = await user_repo.add(
                    Usuario(email="rec_only@taller.com", nombre="Recep", password_hash="h", activo=True)
                )
                assert (
                    target_admin.id is not None
                    and revoked_admin.id is not None
                    and expired_admin.id is not None
                    and inactive_admin.id is not None
                    and recepcion_only.id is not None
                )

                await rol_repo.add(AsignacionRol(usuario_id=target_admin.id, rol=RolEnum.ADMIN, desde=now))
                await rol_repo.add(
                    AsignacionRol(
                        usuario_id=revoked_admin.id,
                        rol=RolEnum.ADMIN,
                        desde=now - timedelta(days=2),
                        revocada_en=now - timedelta(hours=1),
                    )
                )
                await rol_repo.add(
                    AsignacionRol(
                        usuario_id=expired_admin.id,
                        rol=RolEnum.ADMIN,
                        desde=now - timedelta(days=2),
                        vence_en=now - timedelta(seconds=1),
                    )
                )
                await rol_repo.add(AsignacionRol(usuario_id=inactive_admin.id, rol=RolEnum.ADMIN, desde=now))
                await rol_repo.add(AsignacionRol(usuario_id=recepcion_only.id, rol=RolEnum.RECEPCION, desde=now))

                # Act & Assert: ninguno de los otros califica como ADMIN activo vigente -> 0
                assert await rol_repo.count_other_active_admins(target_admin.id, now=now) == 0

                # Agregamos dos administradores activos vigentes (uno sin vencimiento y otro con vencimiento futuro)
                valid_admin_1 = await user_repo.add(
                    Usuario(email="adm_valid1@taller.com", nombre="Valid 1", password_hash="h", activo=True)
                )
                valid_admin_2 = await user_repo.add(
                    Usuario(email="adm_valid2@taller.com", nombre="Valid 2", password_hash="h", activo=True)
                )
                assert valid_admin_1.id is not None and valid_admin_2.id is not None

                await rol_repo.add(AsignacionRol(usuario_id=valid_admin_1.id, rol=RolEnum.ADMIN, desde=now))
                await rol_repo.add(
                    AsignacionRol(
                        usuario_id=valid_admin_2.id,
                        rol=RolEnum.ADMIN,
                        desde=now,
                        vence_en=now + timedelta(days=10),
                    )
                )

                assert await rol_repo.count_other_active_admins(target_admin.id, now=now) == 2
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_usuarios_admin_create_and_list_roles_happy_path() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
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
                admin_user = Usuario(
                    email="admin_t41@taller.com",
                    nombre="Admin T41",
                    password_hash="hash_admin",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add(admin_user)
                await session.flush()
                assert admin_user.id is not None
                admin_id = admin_user.id

                session.add(AsignacionRol(usuario_id=admin_id, rol=RolEnum.ADMIN))
                await session.commit()

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                async def _override_current_user() -> Usuario:
                    return admin_user

                app.dependency_overrides[get_session] = _override_session
                app.dependency_overrides[get_current_user] = _override_current_user

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # Act: POST /usuarios
                    res_create = await client.post(
                        "/usuarios",
                        json={
                            "email": "nuevo_staff@taller.com",
                            "nombre": "Nuevo Staff",
                            "password": "ClaveProvisoriaStaff1!",
                        },
                    )

                    # Assert: 201 Created, debe_cambiar_password=True, sin password_hash, evento registrado
                    assert res_create.status_code == 201
                    body_create = res_create.json()
                    assert body_create["email"] == "nuevo_staff@taller.com"
                    assert body_create["nombre"] == "Nuevo Staff"
                    assert body_create["activo"] is True
                    assert body_create["debe_cambiar_password"] is True
                    assert body_create["roles"] == []
                    assert "password_hash" not in body_create
                    new_user_id = body_create["id"]

                    ev = (
                        await session.execute(
                            select(EventoSeguridad).where(
                                EventoSeguridad.actor == "admin_t41@taller.com"
                            )
                        )
                    ).scalars().first()
                    assert ev is not None
                    assert "nuevo_staff@taller.com" in ev.accion

                    # Act: GET /usuarios/{id}/roles para admin_id y new_user_id
                    res_roles_admin = await client.get(f"/usuarios/{admin_id}/roles")
                    assert res_roles_admin.status_code == 200
                    roles_admin_list = res_roles_admin.json()
                    assert len(roles_admin_list) == 1
                    assert roles_admin_list[0]["rol"] == "ADMIN"
                    assert roles_admin_list[0]["usuario_id"] == admin_id

                    res_roles_new = await client.get(f"/usuarios/{new_user_id}/roles")
                    assert res_roles_new.status_code == 200
                    assert res_roles_new.json() == []
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_usuarios_admin_create_and_list_roles_errors_403_404_409_422() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
    from app.modules.usuarios.models import AsignacionRol, RolEnum, Usuario
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
                admin_user = Usuario(
                    email="admin_err_t41@taller.com",
                    nombre="Admin Err",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                recepcion_user = Usuario(
                    email="recep_err_t41@taller.com",
                    nombre="Recep Err",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add_all([admin_user, recepcion_user])
                await session.flush()
                assert admin_user.id is not None and recepcion_user.id is not None

                session.add_all(
                    [
                        AsignacionRol(usuario_id=admin_user.id, rol=RolEnum.ADMIN),
                        AsignacionRol(usuario_id=recepcion_user.id, rol=RolEnum.RECEPCION),
                    ]
                )
                await session.commit()

                actor: dict[str, Usuario] = {"user": admin_user}

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                async def _override_current_user() -> Usuario:
                    return actor["user"]

                app.dependency_overrides[get_session] = _override_session
                app.dependency_overrides[get_current_user] = _override_current_user

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 1. Email duplicado -> 409 Conflict (RN-01)
                    res_dup = await client.post(
                        "/usuarios",
                        json={
                            "email": "admin_err_t41@taller.com",
                            "nombre": "Otro",
                            "password": "ClaveValida1!",
                        },
                    )
                    assert res_dup.status_code == 409

                    # 2. Campos extra o contraseña > 72 bytes UTF-8 -> 422 Unprocessable Entity
                    res_extra = await client.post(
                        "/usuarios",
                        json={
                            "email": "extra_u@taller.com",
                            "nombre": "Extra",
                            "password": "ClaveValida1!",
                            "activo": False,
                        },
                    )
                    assert res_extra.status_code == 422

                    res_pwd_long = await client.post(
                        "/usuarios",
                        json={
                            "email": "long_u@taller.com",
                            "nombre": "Long",
                            "password": "ñ" * 40,
                        },
                    )
                    assert res_pwd_long.status_code == 422

                    # 3. GET /usuarios/{id}/roles sobre usuario inexistente -> 404 Not Found
                    res_404 = await client.get("/usuarios/999999/roles")
                    assert res_404.status_code == 404

                    # 4. Usuario sin rol ADMIN (RECEPCION) -> 403 Forbidden
                    actor["user"] = recepcion_user
                    res_403_post = await client.post(
                        "/usuarios",
                        json={
                            "email": "intento_recep@taller.com",
                            "nombre": "Intento",
                            "password": "ClaveValida1!",
                        },
                    )
                    assert res_403_post.status_code == 403

                    res_403_get = await client.get(f"/usuarios/{admin_user.id}/roles")
                    assert res_403_get.status_code == 403
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rbac_c09_dynamic_roles_expiration_revocation_and_rn03() -> None:
    from collections.abc import AsyncGenerator
    from datetime import datetime, timedelta, timezone
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.security import hash_password
    from app.modules.clientes.models import Cliente
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
                pwd_hash = await hash_password("ClaveSeguraC09!")
                admin_user = Usuario(
                    email="admin_c09@taller.com",
                    nombre="Admin C09",
                    password_hash=pwd_hash,
                    activo=True,
                    debe_cambiar_password=False,
                )
                staff_user = Usuario(
                    email="recep_c09@taller.com",
                    nombre="Recep C09",
                    password_hash=pwd_hash,
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add_all([admin_user, staff_user])
                await session.flush()
                assert admin_user.id is not None and staff_user.id is not None
                admin_id, staff_id = admin_user.id, staff_user.id

                session.add(AsignacionRol(usuario_id=admin_id, rol=RolEnum.ADMIN))
                cli_demo = Cliente(
                    usuario_id=None,
                    nombre="Cliente Demo C09",
                    documento="DOC-C09-001",
                    telefono="11223344",
                )
                session.add(cli_demo)
                await session.commit()
                assert cli_demo.id is not None
                cli_demo_id = cli_demo.id

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                app.dependency_overrides[get_session] = _override_session

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with (
                    httpx.AsyncClient(transport=transport, base_url="http://test") as admin_client,
                    httpx.AsyncClient(transport=transport, base_url="http://test") as staff_client,
                ):
                    # Login de admin_client
                    r_login_adm = await admin_client.post(
                        "/auth/login",
                        json={"email": "admin_c09@taller.com", "password": "ClaveSeguraC09!"},
                    )
                    assert r_login_adm.status_code == 200

                    # 1. POST /usuarios/{id}/roles asigna RECEPCION -> 201 Created
                    future_dt = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
                    r_asig = await admin_client.post(
                        f"/usuarios/{staff_id}/roles",
                        json={"rol": "RECEPCION", "vence_en": future_dt},
                    )
                    assert r_asig.status_code == 201
                    body_asig = r_asig.json()
                    assert body_asig["usuario_id"] == staff_id
                    assert body_asig["rol"] == "RECEPCION"
                    assert body_asig["otorgada_por"] == admin_id
                    assert body_asig["revocada_en"] is None
                    first_asig_id = body_asig["id"]

                    # 2. RN-03: intentar asignar el mismo rol vigente de nuevo -> 409 Conflict
                    r_dup_rol = await admin_client.post(
                        f"/usuarios/{staff_id}/roles",
                        json={"rol": "RECEPCION"},
                    )
                    assert r_dup_rol.status_code == 409

                    # 3. Validaciones de vence_en: sin timezone (naive) o en el pasado -> 422 Unprocessable Entity
                    r_naive = await admin_client.post(
                        f"/usuarios/{staff_id}/roles",
                        json={"rol": "MECANICO", "vence_en": "2099-05-01T10:00:00"},
                    )
                    assert r_naive.status_code == 422

                    past_dt = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
                    r_past = await admin_client.post(
                        f"/usuarios/{staff_id}/roles",
                        json={"rol": "MECANICO", "vence_en": past_dt},
                    )
                    assert r_past.status_code == 422

                    # 4. Staff inicia sesión cuando tiene RECEPCION vigente y accede a endpoint de RECEPCION (200 OK)
                    r_login_staff = await staff_client.post(
                        "/auth/login",
                        json={"email": "recep_c09@taller.com", "password": "ClaveSeguraC09!"},
                    )
                    assert r_login_staff.status_code == 200

                    r_cli_ok = await staff_client.get(f"/clientes/{cli_demo_id}")
                    assert r_cli_ok.status_code == 200

                    # 5. Caso C-09: Admin revoca RECEPCION con DELETE /usuarios/{id}/roles/RECEPCION -> 200 OK
                    r_rev = await admin_client.delete(f"/usuarios/{staff_id}/roles/RECEPCION")
                    assert r_rev.status_code == 200
                    body_rev = r_rev.json()
                    assert body_rev["id"] == first_asig_id
                    assert body_rev["revocada_en"] is not None

                    # Reutilizando la MISMA cookie access_token, staff recibe 403 inmediato en /clientes/{id} (RN-04)
                    r_cli_403 = await staff_client.get(f"/clientes/{cli_demo_id}")
                    assert r_cli_403.status_code == 403

                    # Y GET /auth/yo expone la diferencia: roles=[] (en DB) vs roles_token=["RECEPCION"] (en JWT)
                    r_yo = await staff_client.get("/auth/yo")
                    assert r_yo.status_code == 200
                    yo_data = r_yo.json()
                    assert yo_data["roles"] == []
                    assert yo_data["roles_token"] == ["RECEPCION"]

                    # 6. Caso C-09 vencimiento y reasignación de rol vencido:
                    # Insertamos una asignación abierta de MECANICO para staff_id cuyo vence_en ya expiró
                    expired_asig = AsignacionRol(
                        usuario_id=staff_id,
                        rol=RolEnum.MECANICO,
                        desde=datetime.now(timezone.utc) - timedelta(days=2),
                        vence_en=datetime.now(timezone.utc) - timedelta(seconds=5),
                        revocada_en=None,
                        otorgada_por=admin_id,
                    )
                    session.add(expired_asig)
                    await session.commit()
                    assert expired_asig.id is not None
                    expired_asig_id = expired_asig.id

                    # Reasignar MECANICO por POST /usuarios/{id}/roles cierra la fila vencida y crea una nueva activa (201)
                    r_reasig = await admin_client.post(
                        f"/usuarios/{staff_id}/roles",
                        json={"rol": "MECANICO"},
                    )
                    assert r_reasig.status_code == 201
                    new_mec_id = r_reasig.json()["id"]
                    assert new_mec_id != expired_asig_id

                    # GET /usuarios/{id}/roles conserva las 3 filas históricas (RECEPCION revocada, MECANICO vencida cerrada, MECANICO nueva)
                    r_hist = await admin_client.get(f"/usuarios/{staff_id}/roles")
                    assert r_hist.status_code == 200
                    hist = r_hist.json()
                    assert len(hist) == 3
                    by_id = {item["id"]: item for item in hist}
                    assert by_id[first_asig_id]["revocada_en"] is not None
                    assert by_id[expired_asig_id]["revocada_en"] is not None
                    assert by_id[new_mec_id]["revocada_en"] is None

                    # Verificar registro en evento_seguridad
                    evs = (
                        await session.execute(
                            select(EventoSeguridad).where(
                                EventoSeguridad.actor == "admin_c09@taller.com"
                            )
                        )
                    ).scalars().all()
                    assert len(evs) >= 3
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rbac_c10_admin_self_protection_rn05_and_expiration_denial() -> None:
    from collections.abc import AsyncGenerator
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    import httpx
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
    from app.core.unit_of_work import UnitOfWork
    from app.modules.clientes.models import Cliente
    from app.modules.usuarios.models import AsignacionRol, RolEnum, Usuario
    from app.modules.usuarios.service import UsuariosService
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
                now = datetime.now(timezone.utc)
                # Limpiar otros ADMIN activos del entorno para probar exactamente el conteo de últimos ADMIN (RN-05)
                await session.execute(
                    update(AsignacionRol)
                    .where(AsignacionRol.rol == RolEnum.ADMIN)
                    .where(AsignacionRol.revocada_en.is_(None))
                    .values(revocada_en=now - timedelta(days=1))
                )

                admin_1 = Usuario(
                    email="admin1_c10@taller.com",
                    nombre="Admin 1 C10",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                admin_2 = Usuario(
                    email="admin2_c10@taller.com",
                    nombre="Admin 2 C10",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                temp_recep = Usuario(
                    email="temp_recep_c10@taller.com",
                    nombre="Temp Recep",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add_all([admin_1, admin_2, temp_recep])
                await session.flush()
                assert admin_1.id is not None and admin_2.id is not None and temp_recep.id is not None
                a1_id, a2_id, tr_id = admin_1.id, admin_2.id, temp_recep.id

                asig_tr = AsignacionRol(
                    usuario_id=tr_id,
                    rol=RolEnum.RECEPCION,
                    desde=now - timedelta(hours=2),
                    vence_en=now + timedelta(hours=1),
                )
                session.add_all(
                    [
                        AsignacionRol(usuario_id=a1_id, rol=RolEnum.ADMIN, desde=now),
                        AsignacionRol(usuario_id=a2_id, rol=RolEnum.ADMIN, desde=now),
                        asig_tr,
                    ]
                )
                cli = Cliente(
                    usuario_id=None,
                    nombre="Cli C10",
                    documento="DOC-C10-001",
                    telefono="123456",
                )
                session.add(cli)
                await session.commit()
                assert asig_tr.id is not None and cli.id is not None
                asig_tr_id, cli_id = asig_tr.id, cli.id

                actor: dict[str, Usuario] = {"user": admin_1}

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                async def _override_current_user() -> Usuario:
                    return actor["user"]

                app.dependency_overrides[get_session] = _override_session
                app.dependency_overrides[get_current_user] = _override_current_user

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 1. Caso C-10 / RN-05 #1: Admin 1 intenta revocarse su propio rol ADMIN (aun existiendo Admin 2) -> 409 Conflict
                    r_self_rev = await client.delete(f"/usuarios/{a1_id}/roles/ADMIN")
                    assert r_self_rev.status_code == 409

                    # 2. Caso C-10: Admin 1 revoca el rol ADMIN de Admin 2 (queda Admin 1 activo) -> 200 OK
                    r_rev_a2 = await client.delete(f"/usuarios/{a2_id}/roles/ADMIN")
                    assert r_rev_a2.status_code == 200
                    assert r_rev_a2.json()["revocada_en"] is not None

                    # Revocar nuevamente el mismo rol ya revocado de Admin 2 -> 404 Not Found
                    r_rev_a2_again = await client.delete(f"/usuarios/{a2_id}/roles/ADMIN")
                    assert r_rev_a2_again.status_code == 404

                    # 3. Caso C-10 / RN-05 #2: Ahora Admin 1 es el ÚNICO administrador activo vigente.
                    # Si otro actor (ej. Admin 2 en una petición concurrente o servicio) intenta revocar el rol ADMIN de Admin 1 -> 409 Conflict
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as svc_session:
                        svc = UsuariosService(UnitOfWork(svc_session))
                        with pytest.raises(HTTPException) as exc_last_admin:
                            await svc.revocar_rol(admin_2, a1_id, RolEnum.ADMIN)
                        assert exc_last_admin.value.status_code == 409

                    # 4. Casos 404 en POST y DELETE de roles sobre usuario inexistente
                    r_post_404 = await client.post("/usuarios/999999/roles", json={"rol": "MECANICO"})
                    assert r_post_404.status_code == 404

                    r_del_404 = await client.delete("/usuarios/999999/roles/MECANICO")
                    assert r_del_404.status_code == 404

                    # 5. Caso C-09 expiración por vence_en: temp_recep accede mientras vence_en > now (200),
                    # pero al vencer vence_en <= now recibe 403 inmediato sin que revocada_en haya cambiado
                    actor["user"] = temp_recep
                    r_before_exp = await client.get(f"/clientes/{cli_id}")
                    assert r_before_exp.status_code == 200

                    await session.execute(
                        update(AsignacionRol)
                        .where(AsignacionRol.id == asig_tr_id)
                        .values(vence_en=datetime.now(timezone.utc) - timedelta(seconds=5))
                    )
                    await session.commit()

                    r_after_exp = await client.get(f"/clientes/{cli_id}")
                    assert r_after_exp.status_code == 403
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_eventos_seguridad_paginacion_admin_happy_path() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
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
                admin_user = Usuario(
                    email="admin_ev@taller.com",
                    nombre="Admin Eventos",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add(admin_user)
                await session.flush()
                assert admin_user.id is not None

                session.add(AsignacionRol(usuario_id=admin_user.id, rol=RolEnum.ADMIN))
                for idx in range(1, 4):
                    session.add(
                        EventoSeguridad(
                            actor="admin_ev@taller.com",
                            accion=f"Acción auditada #{idx}",
                        )
                    )
                await session.commit()

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                async def _override_current_user() -> Usuario:
                    return admin_user

                app.dependency_overrides[get_session] = _override_session
                app.dependency_overrides[get_current_user] = _override_current_user

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # Act
                    res = await client.get("/eventos?page=1&size=2")

                    # Assert
                    assert res.status_code == 200
                    body = res.json()
                    assert "items" in body
                    assert len(body["items"]) == 2
                    assert body["total"] >= 3
                    assert body["page"] == 1
                    assert body["size"] == 2
                    assert body["pages"] >= 2
                    assert "cuando" in body["items"][0]
                    assert "actor" in body["items"][0]
                    assert "accion" in body["items"][0]
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rbac_c11_client_isolation_rn17_rn06_and_eventos_out_of_range_422() -> None:
    from collections.abc import AsyncGenerator
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.usuarios.models import AsignacionRol, RolEnum, Usuario
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
                admin_user = Usuario(
                    email="admin_c11@taller.com",
                    nombre="Admin C11",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                admin_provisorio = Usuario(
                    email="admin_prov_c11@taller.com",
                    nombre="Admin Provisorio",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=True,
                )
                user_cli_a = Usuario(
                    email="clia_c11@taller.com",
                    nombre="Cliente A",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                user_cli_b = Usuario(
                    email="clib_c11@taller.com",
                    nombre="Cliente B",
                    password_hash="h",
                    activo=True,
                    debe_cambiar_password=False,
                )
                session.add_all([admin_user, admin_provisorio, user_cli_a, user_cli_b])
                await session.flush()
                assert (
                    admin_user.id is not None
                    and admin_provisorio.id is not None
                    and user_cli_a.id is not None
                    and user_cli_b.id is not None
                )

                session.add_all(
                    [
                        AsignacionRol(usuario_id=admin_user.id, rol=RolEnum.ADMIN),
                        AsignacionRol(usuario_id=admin_provisorio.id, rol=RolEnum.ADMIN),
                        AsignacionRol(usuario_id=user_cli_a.id, rol=RolEnum.CLIENTE),
                        AsignacionRol(usuario_id=user_cli_b.id, rol=RolEnum.CLIENTE),
                    ]
                )
                cli_a = Cliente(
                    usuario_id=user_cli_a.id,
                    nombre="Cliente A",
                    documento="DOC-C11-A",
                    telefono="111",
                )
                cli_b = Cliente(
                    usuario_id=user_cli_b.id,
                    nombre="Cliente B",
                    documento="DOC-C11-B",
                    telefono="222",
                )
                session.add_all([cli_a, cli_b])
                await session.flush()
                assert cli_a.id is not None and cli_b.id is not None

                session.add_all(
                    [
                        Vehiculo(
                            cliente_id=cli_a.id,
                            patente="C11AA1",
                            marca="Ford",
                            modelo="Focus",
                            anio=2020,
                        ),
                        Vehiculo(
                            cliente_id=cli_b.id,
                            patente="C11BB2",
                            marca="Honda",
                            modelo="Civic",
                            anio=2021,
                        ),
                    ]
                )
                await session.commit()

                actor: dict[str, Usuario] = {"user": user_cli_a}

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                async def _override_current_user() -> Usuario:
                    return actor["user"]

                app.dependency_overrides[get_session] = _override_session
                app.dependency_overrides[get_current_user] = _override_current_user

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 1. Caso C-11 / RN-17: Cliente A solo ve su vehículo C11AA1 y nunca el de Cliente B
                    actor["user"] = user_cli_a
                    r_mis_a = await client.get("/mis-vehiculos")
                    assert r_mis_a.status_code == 200
                    patentes_a = [v["patente"] for v in r_mis_a.json()]
                    assert patentes_a == ["C11AA1"]

                    # Cliente A no puede consultar /clientes/{cli_b.id} ni /eventos -> 403 Forbidden
                    assert (await client.get(f"/clientes/{cli_b.id}")).status_code == 403
                    assert (await client.get("/eventos")).status_code == 403

                    # Cliente B solo ve su vehículo C11BB2
                    actor["user"] = user_cli_b
                    r_mis_b = await client.get("/mis-vehiculos")
                    assert r_mis_b.status_code == 200
                    patentes_b = [v["patente"] for v in r_mis_b.json()]
                    assert patentes_b == ["C11BB2"]

                    # 2. RN-06: Admin con debe_cambiar_password=True bloqueado en cualquier ruta de router_protegido -> 403
                    actor["user"] = admin_provisorio
                    assert (await client.get("/eventos")).status_code == 403
                    assert (await client.get("/mis-vehiculos")).status_code == 403
                    assert (
                        await client.post(
                            "/usuarios",
                            json={
                                "email": "bloqueado@taller.com",
                                "nombre": "Bloq",
                                "password": "ClaveValida1!",
                            },
                        )
                    ).status_code == 403

                    # 3. Admin activo: GET /eventos con page < 1, size > 100 o page > pages -> 422 Unprocessable Entity
                    actor["user"] = admin_user
                    assert (await client.get("/eventos?page=0")).status_code == 422
                    assert (await client.get("/eventos?size=0")).status_code == 422
                    assert (await client.get("/eventos?size=101")).status_code == 422
                    assert (await client.get("/eventos?page=99999&size=20")).status_code == 422
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()
