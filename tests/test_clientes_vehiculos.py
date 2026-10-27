import pytest
from pydantic import ValidationError
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401


def test_clientes_and_vehiculos_schemas_validation_and_extra_forbid() -> None:
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.clientes.schemas import (
        ClienteResponse,
        CrearClienteRequest,
        CrearVehiculoRequest,
        VehiculoResponse,
    )

    # 1. CrearClienteRequest valido
    req_c = CrearClienteRequest(
        nombre="Juan Pérez",
        documento="30111222",
        telefono="1144556677",
    )
    assert req_c.nombre == "Juan Pérez"
    assert req_c.documento == "30111222"
    assert req_c.telefono == "1144556677"

    # Rechazo por campo extra no declarado (Regla Dura #1: extra="forbid")
    with pytest.raises(ValidationError):
        CrearClienteRequest(
            nombre="Juan Pérez",
            documento="30111222",
            telefono="1144556677",
            usuario_id=99,  # type: ignore[call-arg]
        )

    # 2. CrearVehiculoRequest valido (incluyendo bordes 1950 y 2100)
    req_v_min = CrearVehiculoRequest(
        patente="AA123BB",
        marca="Ford",
        modelo="Falcon",
        anio=1950,
    )
    req_v_max = CrearVehiculoRequest(
        patente="AF999ZZ",
        marca="Toyota",
        modelo="Hilux",
        anio=2100,
    )
    assert req_v_min.anio == 1950
    assert req_v_max.anio == 2100

    # Rechazo por anio fuera de rango (1949 y 2101)
    with pytest.raises(ValidationError):
        CrearVehiculoRequest(
            patente="AA123BB",
            marca="Ford",
            modelo="T",
            anio=1949,
        )

    with pytest.raises(ValidationError):
        CrearVehiculoRequest(
            patente="AA123BB",
            marca="Ford",
            modelo="Future",
            anio=2101,
        )

    # Rechazo por campo extra en CrearVehiculoRequest
    with pytest.raises(ValidationError):
        CrearVehiculoRequest(
            patente="AA123BB",
            marca="Ford",
            modelo="Focus",
            anio=2020,
            borrado_en=None,  # type: ignore[call-arg]
        )

    # 3. Serializacion desde atributos ORM (from_attributes=True)
    orm_cliente = Cliente(
        id=10,
        usuario_id=None,
        nombre="María Gómez",
        documento="28999888",
        telefono="1199887766",
    )
    orm_vehiculo = Vehiculo(
        id=5,
        cliente_id=10,
        patente="AB456CD",
        marca="Peugeot",
        modelo="208",
        anio=2023,
    )
    orm_cliente.vehiculos = [orm_vehiculo]

    v_resp = VehiculoResponse.model_validate(orm_vehiculo)
    assert v_resp.id == 5
    assert v_resp.cliente_id == 10
    assert v_resp.patente == "AB456CD"

    c_resp = ClienteResponse.model_validate(orm_cliente)
    assert c_resp.id == 10
    assert c_resp.usuario_id is None
    assert len(c_resp.vehiculos) == 1
    assert c_resp.vehiculos[0].patente == "AB456CD"


@pytest.mark.asyncio
async def test_cliente_repository_queries_and_selectinload_active_vehiculos() -> None:
    from datetime import datetime, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.clientes.repository import ClienteRepository
    from app.modules.usuarios.models import Usuario

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            repo = ClienteRepository(session)
            user = Usuario(
                email="cliente_repo_test@example.com",
                nombre="Cliente Con Usuario",
                password_hash="hash_test",
            )
            session.add(user)
            await session.flush()
            assert user.id is not None

            cliente = await repo.add(
                Cliente(
                    usuario_id=user.id,
                    nombre="Cliente Flota",
                    documento="DOC-CLI-REPO-1",
                    telefono="1122334455",
                )
            )
            assert cliente.id is not None

            # Vehiculo activo y vehiculo dado de baja
            v_activo = Vehiculo(
                cliente_id=cliente.id,
                patente="ACT123",
                marca="Renault",
                modelo="Clio",
                anio=2018,
            )
            v_baja = Vehiculo(
                cliente_id=cliente.id,
                patente="BAJ999",
                marca="Fiat",
                modelo="Uno",
                anio=2010,
                borrado_en=datetime.now(timezone.utc),
            )
            session.add_all([v_activo, v_baja])
            await session.flush()

            # 1. get_by_documento
            by_doc = await repo.get_by_documento("DOC-CLI-REPO-1")
            assert by_doc is not None
            assert by_doc.id == cliente.id
            assert await repo.get_by_documento("INEXISTENTE") is None

            # 2. get_by_usuario_id
            by_usr = await repo.get_by_usuario_id(user.id)
            assert by_usr is not None
            assert by_usr.id == cliente.id
            assert await repo.get_by_usuario_id(999999) is None

            # 3. get_by_id_with_vehiculos con selectinload de activos solamente
            session.expunge_all()
            loaded = await repo.get_by_id_with_vehiculos(cliente.id)
            assert loaded is not None
            assert len(loaded.vehiculos) == 1
            assert loaded.vehiculos[0].patente == "ACT123"

            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_vehiculo_repository_and_uow_integration() -> None:
    from datetime import datetime, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.core.unit_of_work import UnitOfWork
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.clientes.repository import VehiculoRepository
    from app.modules.clientes.unit_of_work import ClientesUnitOfWork
    from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # Verificar exposicion de clientes y vehiculos en UnitOfWork y ClientesUnitOfWork
            uow = ClientesUnitOfWork(session)
            assert isinstance(uow, UnitOfWork)
            async with uow as active_uow:
                assert hasattr(active_uow, "clientes")
                assert hasattr(active_uow, "vehiculos")
                assert isinstance(active_uow.vehiculos, VehiculoRepository)
                # No hacemos commit real todavia; salimos del bloque vacio

            vehiculo_repo = VehiculoRepository(session)

            # Crear cliente y dos vehiculos (uno activo y uno dado de baja)
            c1 = Cliente(nombre="Carlos Flota", documento="DOC-VEH-REPO-1", telefono="1100001111")
            c2 = Cliente(nombre="Ana Flota", documento="DOC-VEH-REPO-2", telefono="1100002222")
            session.add_all([c1, c2])
            await session.flush()
            assert c1.id is not None and c2.id is not None

            v_activo = await vehiculo_repo.add(
                Vehiculo(
                    cliente_id=c1.id,
                    patente="PAT001",
                    marca="Volkswagen",
                    modelo="Golf",
                    anio=2019,
                )
            )
            v_baja = await vehiculo_repo.add(
                Vehiculo(
                    cliente_id=c1.id,
                    patente="PAT002",
                    marca="Chevrolet",
                    modelo="Cruze",
                    anio=2017,
                    borrado_en=datetime.now(timezone.utc),
                )
            )
            v_otro = await vehiculo_repo.add(
                Vehiculo(
                    cliente_id=c2.id,
                    patente="PAT003",
                    marca="Mazda",
                    modelo="3",
                    anio=2021,
                )
            )
            assert v_activo.id is not None and v_baja.id is not None and v_otro.id is not None

            # 1. get_by_patente_activa
            found = await vehiculo_repo.get_by_patente_activa("PAT001")
            assert found is not None and found.id == v_activo.id
            assert await vehiculo_repo.get_by_patente_activa("PAT002") is None

            # 2. list_by_cliente_id (solo activos del cliente c1)
            flota_c1 = await vehiculo_repo.list_by_cliente_id(c1.id)
            assert len(flota_c1) == 1
            assert flota_c1[0].id == v_activo.id

            # 3. has_open_orders (RN-16: EstadoOrden.es_final == False)
            est_abierto = EstadoOrden(
                codigo="EN_REP_TEST",
                descripcion="En reparacion test",
                posicion=91,
                es_final=False,
            )
            est_final = EstadoOrden(
                codigo="TERM_TEST",
                descripcion="Terminada test",
                posicion=92,
                es_final=True,
            )
            session.add_all([est_abierto, est_final])
            await session.flush()

            assert await vehiculo_repo.has_open_orders(v_activo.id) is False

            # Orden en estado final -> NO bloquea (has_open_orders == False)
            orden_cerrada = OrdenTrabajo(
                vehiculo_id=v_activo.id,
                estado="TERM_TEST",
                falla="Cambio de aceite",
            )
            session.add(orden_cerrada)
            await session.flush()
            assert await vehiculo_repo.has_open_orders(v_activo.id) is False

            # Orden en estado no final -> SI bloquea (has_open_orders == True)
            orden_abierta = OrdenTrabajo(
                vehiculo_id=v_activo.id,
                estado="EN_REP_TEST",
                falla="Frenos",
            )
            session.add(orden_abierta)
            await session.flush()
            assert await vehiculo_repo.has_open_orders(v_activo.id) is True

            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clientes_service_create_get_and_register_vehiculo_with_rn01() -> None:
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.schemas import CrearClienteRequest, CrearVehiculoRequest
    from app.modules.clientes.service import ClientesService
    from app.modules.clientes.unit_of_work import ClientesUnitOfWork

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
                uow = ClientesUnitOfWork(session)
                service = ClientesService(uow)

                # 1. Crear cliente (201)
                c1 = await service.crear_cliente(
                    CrearClienteRequest(
                        nombre="Pedro Taller",
                        documento="DOC-SVC-001",
                        telefono="1133334444",
                    )
                )
                assert c1.id is not None
                c1_id = c1.id
                assert c1.usuario_id is None

                # 2. Documento duplicado -> 409 Conflict (RN-01)
                with pytest.raises(HTTPException) as exc_dup_doc:
                    await service.crear_cliente(
                        CrearClienteRequest(
                            nombre="Otro Pedro",
                            documento="DOC-SVC-001",
                            telefono="1199990000",
                        )
                    )
                assert exc_dup_doc.value.status_code == 409

                # 3. Registrar vehiculo en cliente inexistente -> 404 Not Found
                with pytest.raises(HTTPException) as exc_no_cli:
                    await service.registrar_vehiculo(
                        999999,
                        CrearVehiculoRequest(
                            patente="SVC111",
                            marca="Ford",
                            modelo="Ka",
                            anio=2020,
                        ),
                    )
                assert exc_no_cli.value.status_code == 404

                # 4. Registrar vehiculo valido en c1
                v1 = await service.registrar_vehiculo(
                    c1_id,
                    CrearVehiculoRequest(
                        patente="SVC111",
                        marca="Ford",
                        modelo="Ka",
                        anio=2020,
                    ),
                )
                assert v1.id is not None
                v1_id = v1.id
                assert v1.cliente_id == c1_id

                # 5. Patente activa duplicada -> 409 Conflict (RN-01)
                c2 = await service.crear_cliente(
                    CrearClienteRequest(
                        nombre="Lucia Compradora",
                        documento="DOC-SVC-002",
                        telefono="1155556666",
                    )
                )
                assert c2.id is not None
                c2_id = c2.id

                with pytest.raises(HTTPException) as exc_dup_pat:
                    await service.registrar_vehiculo(
                        c2_id,
                        CrearVehiculoRequest(
                            patente="SVC111",
                            marca="Ford",
                            modelo="Ka",
                            anio=2020,
                        ),
                    )
                assert exc_dup_pat.value.status_code == 409

                # 6. Si v1 se da de baja logicamente (venta), c2 PUEDE registrar la misma patente (RN-01)
                await uow.vehiculos.soft_delete(v1_id)
                await session.commit()

                v1_revendido = await service.registrar_vehiculo(
                    c2_id,
                    CrearVehiculoRequest(
                        patente="SVC111",
                        marca="Ford",
                        modelo="Ka",
                        anio=2020,
                    ),
                )
                assert v1_revendido.id is not None
                assert v1_revendido.id != v1_id
                assert v1_revendido.cliente_id == c2_id

                # 7. Obtener cliente con vehiculos activos: c1 tiene 0 activos, c2 tiene 1 activo
                c1_detail = await service.obtener_cliente(c1_id)
                assert len(c1_detail.vehiculos) == 0

                c2_detail = await service.obtener_cliente(c2_id)
                assert len(c2_detail.vehiculos) == 1
                assert c2_detail.vehiculos[0].patente == "SVC111"

                # Cliente inexistente -> 404
                with pytest.raises(HTTPException) as exc_404:
                    await service.obtener_cliente(999999)
                assert exc_404.value.status_code == 404
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clientes_service_soft_delete_rn16_and_mis_vehiculos_rn17() -> None:
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente
    from app.modules.clientes.schemas import CrearVehiculoRequest
    from app.modules.clientes.service import ClientesService
    from app.modules.clientes.unit_of_work import ClientesUnitOfWork
    from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo
    from app.modules.usuarios.models import Usuario

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
                uow = ClientesUnitOfWork(session)
                service = ClientesService(uow)

                # Crear dos usuarios con sus respectivos clientes (RN-17)
                u1 = Usuario(email="cli1_rn17@example.com", nombre="Cliente 1", password_hash="h1")
                u2 = Usuario(email="cli2_rn17@example.com", nombre="Cliente 2", password_hash="h2")
                u_sin_cliente = Usuario(email="staff@example.com", nombre="Staff", password_hash="h3")
                session.add_all([u1, u2, u_sin_cliente])
                await session.flush()
                assert u1.id is not None and u2.id is not None and u_sin_cliente.id is not None
                u1_id, u2_id, u_sin_id = u1.id, u2.id, u_sin_cliente.id

                c1 = Cliente(usuario_id=u1_id, nombre="Cliente 1", documento="DOC-RN17-1", telefono="111")
                c2 = Cliente(usuario_id=u2_id, nombre="Cliente 2", documento="DOC-RN17-2", telefono="222")
                session.add_all([c1, c2])
                await session.commit()
                assert c1.id is not None and c2.id is not None
                c1_id, c2_id = c1.id, c2.id

                v1 = await service.registrar_vehiculo(
                    c1_id,
                    CrearVehiculoRequest(patente="RN16A", marca="Toyota", modelo="Yaris", anio=2021),
                )
                v2 = await service.registrar_vehiculo(
                    c1_id,
                    CrearVehiculoRequest(patente="RN16B", marca="Toyota", modelo="Etios", anio=2022),
                )
                v_ajeno = await service.registrar_vehiculo(
                    c2_id,
                    CrearVehiculoRequest(patente="RN17Z", marca="Honda", modelo="Fit", anio=2020),
                )
                assert v1.id is not None and v2.id is not None and v_ajeno.id is not None
                v1_id, v2_id = v1.id, v_ajeno.id
                v2_c1_id = v2.id

                # Estados de orden (es_final False vs True)
                est_pend = EstadoOrden(
                    codigo="PEND_SVC",
                    descripcion="Pendiente",
                    posicion=81,
                    es_final=False,
                )
                est_term = EstadoOrden(
                    codigo="TERM_SVC",
                    descripcion="Terminada",
                    posicion=82,
                    es_final=True,
                )
                session.add_all([est_pend, est_term])
                await session.commit()

                # Orden abierta sobre v1 -> bloquea baja con 409 (RN-16)
                ot_abierta = OrdenTrabajo(vehiculo_id=v1_id, estado="PEND_SVC", falla="Ruido motor")
                session.add(ot_abierta)
                await session.commit()

                with pytest.raises(HTTPException) as exc_open:
                    await service.eliminar_vehiculo(v1_id)
                assert exc_open.value.status_code == 409

                # Pasar la orden a estado final (es_final = True) -> ahora permite baja logica
                ot_abierta.estado = "TERM_SVC"
                session.add(ot_abierta)
                await session.commit()

                await service.eliminar_vehiculo(v1_id)

                # Intentar eliminar de nuevo el mismo vehiculo ya dado de baja -> 404
                with pytest.raises(HTTPException) as exc_already:
                    await service.eliminar_vehiculo(v1_id)
                assert exc_already.value.status_code == 404

                # Vehiculo inexistente -> 404
                with pytest.raises(HTTPException) as exc_not_found:
                    await service.eliminar_vehiculo(999999)
                assert exc_not_found.value.status_code == 404

                # RN-17: listar_mis_vehiculos para u1 devuelve solo v2_c1_id (activo de c1), ni v1 (baja) ni v_ajeno (de c2)
                mis_u1 = await service.listar_mis_vehiculos(u1_id)
                assert len(mis_u1) == 1
                assert mis_u1[0].id == v2_c1_id
                assert mis_u1[0].patente == "RN16B"

                mis_u2 = await service.listar_mis_vehiculos(u2_id)
                assert len(mis_u2) == 1
                assert mis_u2[0].id == v2_id
                assert mis_u2[0].patente == "RN17Z"

                # Usuario sin ficha de cliente -> lista vacia []
                mis_staff = await service.listar_mis_vehiculos(u_sin_id)
                assert mis_staff == []
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clientes_and_vehiculos_http_endpoints_c12_c13_rn01_rn16_rn17() -> None:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
    from app.modules.clientes.models import Cliente
    from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo
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
                # Sembrar usuarios y roles en la sesion de prueba
                recepcion_user = Usuario(
                    email="recep_http@example.com",
                    nombre="Recepcion HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                cliente_user_1 = Usuario(
                    email="cli1_http@example.com",
                    nombre="Cliente HTTP 1",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                cliente_user_2 = Usuario(
                    email="cli2_http@example.com",
                    nombre="Cliente HTTP 2",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                pending_pwd_user = Usuario(
                    email="pending_http@example.com",
                    nombre="Pending HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=True,
                )
                session.add_all([recepcion_user, cliente_user_1, cliente_user_2, pending_pwd_user])
                await session.flush()
                assert (
                    recepcion_user.id is not None
                    and cliente_user_1.id is not None
                    and cliente_user_2.id is not None
                )

                session.add_all(
                    [
                        AsignacionRol(usuario_id=recepcion_user.id, rol=RolEnum.RECEPCION),
                        AsignacionRol(usuario_id=cliente_user_1.id, rol=RolEnum.CLIENTE),
                        AsignacionRol(usuario_id=cliente_user_2.id, rol=RolEnum.CLIENTE),
                    ]
                )
                ficha_cli_1 = Cliente(
                    usuario_id=cliente_user_1.id,
                    nombre="Cliente HTTP 1",
                    documento="DOC-HTTP-CLI1",
                    telefono="111111",
                )
                ficha_cli_2 = Cliente(
                    usuario_id=cliente_user_2.id,
                    nombre="Cliente HTTP 2",
                    documento="DOC-HTTP-CLI2",
                    telefono="222222",
                )
                session.add_all([ficha_cli_1, ficha_cli_2])
                await session.commit()
                assert ficha_cli_1.id is not None and ficha_cli_2.id is not None
                cli1_id, cli2_id = ficha_cli_1.id, ficha_cli_2.id

                from collections.abc import AsyncGenerator

                current_actor: dict[str, Usuario] = {"user": recepcion_user}

                async def _override_session() -> AsyncGenerator[AsyncSession, None]:
                    async with AsyncSession(
                        bind=conn,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ) as req_session:
                        yield req_session

                async def _override_current_user() -> Usuario:
                    return current_actor["user"]

                app.dependency_overrides[get_session] = _override_session

                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    # 0. Sin autenticar (sin cookie access_token y sin override de get_current_user) -> 401
                    res_unauth = await client.get("/mis-vehiculos")
                    assert res_unauth.status_code == 401

                    # Activar override de usuario autenticado
                    app.dependency_overrides[get_current_user] = _override_current_user

                    # 0b. Usuario con debe_cambiar_password=True bloqueado en grupo protegido -> 403 (RN-06)
                    current_actor["user"] = pending_pwd_user
                    res_pending = await client.get("/mis-vehiculos")
                    assert res_pending.status_code == 403

                    # 0c. Usuario con rol CLIENTE intentando POST /clientes -> 403 (RN-04)
                    current_actor["user"] = cliente_user_1
                    res_forbidden = await client.post(
                        "/clientes",
                        json={"nombre": "Intruso", "documento": "DOC-X", "telefono": "123"},
                    )
                    assert res_forbidden.status_code == 403

                    # Cambiar a RECEPCION para gestion de clientes y vehiculos
                    current_actor["user"] = recepcion_user

                    # 1. POST /clientes (201, 409, 422)
                    res_c_201 = await client.post(
                        "/clientes",
                        json={
                            "nombre": "Roberto Mostrador",
                            "documento": "DOC-HTTP-001",
                            "telefono": "1144009988",
                        },
                    )
                    assert res_c_201.status_code == 201
                    created_cli = res_c_201.json()
                    roberto_id = created_cli["id"]
                    assert created_cli["documento"] == "DOC-HTTP-001"
                    assert created_cli["usuario_id"] is None

                    res_c_409 = await client.post(
                        "/clientes",
                        json={
                            "nombre": "Roberto Duplicado",
                            "documento": "DOC-HTTP-001",
                            "telefono": "1100000000",
                        },
                    )
                    assert res_c_409.status_code == 409

                    res_c_422 = await client.post(
                        "/clientes",
                        json={
                            "nombre": "Extra Field",
                            "documento": "DOC-HTTP-999",
                            "telefono": "1100000000",
                            "campo_extra": "prohibido",
                        },
                    )
                    assert res_c_422.status_code == 422

                    # 2. POST /clientes/{id}/vehiculos (201, 404, 409, 422)
                    res_v_404 = await client.post(
                        "/clientes/999999/vehiculos",
                        json={"patente": "HTTP111", "marca": "Ford", "modelo": "Fiesta", "anio": 2018},
                    )
                    assert res_v_404.status_code == 404

                    res_v_422 = await client.post(
                        f"/clientes/{cli1_id}/vehiculos",
                        json={"patente": "HTTP111", "marca": "Ford", "modelo": "Fiesta", "anio": 1940},
                    )
                    assert res_v_422.status_code == 422

                    res_v_201 = await client.post(
                        f"/clientes/{cli1_id}/vehiculos",
                        json={"patente": "HTTP111", "marca": "Ford", "modelo": "Fiesta", "anio": 2018},
                    )
                    assert res_v_201.status_code == 201
                    v1_id = res_v_201.json()["id"]

                    # Segundo vehiculo para cli1 y uno para cli2
                    res_v2_201 = await client.post(
                        f"/clientes/{cli1_id}/vehiculos",
                        json={"patente": "HTTP222", "marca": "VW", "modelo": "Polo", "anio": 2022},
                    )
                    assert res_v2_201.status_code == 201

                    res_v_cli2 = await client.post(
                        f"/clientes/{cli2_id}/vehiculos",
                        json={"patente": "HTTP333", "marca": "Fiat", "modelo": "Cronos", "anio": 2023},
                    )
                    assert res_v_cli2.status_code == 201

                    # Conflicto por patente activa duplicada (409)
                    res_v_409 = await client.post(
                        f"/clientes/{roberto_id}/vehiculos",
                        json={"patente": "HTTP111", "marca": "Ford", "modelo": "Fiesta", "anio": 2018},
                    )
                    assert res_v_409.status_code == 409

                    # 3. GET /clientes/{id} (200 con selectinload de vehiculos activos, 404)
                    res_get_cli1 = await client.get(f"/clientes/{cli1_id}")
                    assert res_get_cli1.status_code == 200
                    cli1_payload = res_get_cli1.json()
                    assert len(cli1_payload["vehiculos"]) == 2

                    res_get_404 = await client.get("/clientes/999999")
                    assert res_get_404.status_code == 404

                    # 4. DELETE /vehiculos/{id} bloqueado si tiene orden abierta (RN-16 -> 409)
                    est_pend = EstadoOrden(
                        codigo="PEND_HTTP",
                        descripcion="Pendiente HTTP",
                        posicion=71,
                        es_final=False,
                    )
                    est_canc = EstadoOrden(
                        codigo="CANC_HTTP",
                        descripcion="Cancelada HTTP",
                        posicion=72,
                        es_final=True,
                    )
                    session.add_all([est_pend, est_canc])
                    await session.flush()

                    ot = OrdenTrabajo(vehiculo_id=v1_id, estado="PEND_HTTP", falla="Bateria")
                    session.add(ot)
                    await session.commit()

                    res_del_409 = await client.delete(f"/vehiculos/{v1_id}")
                    assert res_del_409.status_code == 409

                    # Pasar orden a estado final -> ahora DELETE devuelve 204
                    ot.estado = "CANC_HTTP"
                    session.add(ot)
                    await session.commit()

                    res_del_204 = await client.delete(f"/vehiculos/{v1_id}")
                    assert res_del_204.status_code == 204

                    # Eliminar de nuevo -> 404
                    res_del_404 = await client.delete(f"/vehiculos/{v1_id}")
                    assert res_del_404.status_code == 404

                    # 5. Re-registro de patente HTTP111 vendida a roberto_id -> 201 (RN-01)
                    res_reventa_201 = await client.post(
                        f"/clientes/{roberto_id}/vehiculos",
                        json={"patente": "HTTP111", "marca": "Ford", "modelo": "Fiesta", "anio": 2018},
                    )
                    assert res_reventa_201.status_code == 201

                    # 6. GET /mis-vehiculos con cliente_user_1 devuelve solo HTTP222 (RN-17)
                    current_actor["user"] = cliente_user_1
                    res_mis = await client.get("/mis-vehiculos")
                    assert res_mis.status_code == 200
                    mis_items = res_mis.json()
                    assert len(mis_items) == 1
                    assert mis_items[0]["patente"] == "HTTP222"
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()





