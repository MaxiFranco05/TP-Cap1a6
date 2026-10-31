from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401


# ==============================================================================
# Task 1.1: Tests Unitarios de Esquemas DTO (extra="forbid", validaciones RN-10)
# ==============================================================================

def test_ordenes_schemas_validation_extra_forbid_and_rn10() -> None:
    from app.modules.ordenes.schemas import (
        CrearOrdenRequest,
        EstadoOrdenResponse,
        HistorialEstadoOrdenResponse,
        ItemOrdenDetalleResponse,
        ItemOrdenInput,
        OrdenTrabajoDetalleResponse,
        OrdenTrabajoResumenResponse,
    )

    # 1. ItemOrdenInput valido
    item_in = ItemOrdenInput(repuesto_id=1, cantidad=2)
    assert item_in.repuesto_id == 1
    assert item_in.cantidad == 2

    # Rechazo si cantidad <= 0
    with pytest.raises(ValidationError):
        ItemOrdenInput(repuesto_id=1, cantidad=0)

    # Rechazo si se intenta enviar precio o subtotal (extra="forbid")
    with pytest.raises(ValidationError):
        ItemOrdenInput(repuesto_id=1, cantidad=2, precio_unitario=Decimal("100.00"))  # type: ignore[call-arg]

    # 2. CrearOrdenRequest valido
    req_orden = CrearOrdenRequest(
        vehiculo_id=10,
        falla="Ruido al frenar",
        items=[
            ItemOrdenInput(repuesto_id=1, cantidad=2),
            ItemOrdenInput(repuesto_id=2, cantidad=1),
        ],
    )
    assert req_orden.vehiculo_id == 10
    assert req_orden.falla == "Ruido al frenar"
    assert len(req_orden.items) == 2

    # Rechazo si items esta vacio (RN-10: al menos un ítem)
    with pytest.raises(ValidationError):
        CrearOrdenRequest(vehiculo_id=10, falla="Falla", items=[])

    # Rechazo si hay repuestos repetidos en items (RN-10)
    with pytest.raises(ValidationError):
        CrearOrdenRequest(
            vehiculo_id=10,
            falla="Falla",
            items=[
                ItemOrdenInput(repuesto_id=1, cantidad=2),
                ItemOrdenInput(repuesto_id=1, cantidad=3),
            ],
        )

    # Rechazo si viajan precio, total o estado en CrearOrdenRequest (extra="forbid")
    with pytest.raises(ValidationError):
        CrearOrdenRequest(
            vehiculo_id=10,
            falla="Falla",
            items=[ItemOrdenInput(repuesto_id=1, cantidad=2)],
            total=Decimal("5000.00"),  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        CrearOrdenRequest(
            vehiculo_id=10,
            falla="Falla",
            items=[ItemOrdenInput(repuesto_id=1, cantidad=2)],
            estado="PENDIENTE",  # type: ignore[call-arg]
        )

    # 3. EstadoOrdenResponse from_attributes
    from app.modules.ordenes.models import EstadoOrden
    orm_estado = EstadoOrden(
        codigo="PENDIENTE",
        descripcion="Orden pendiente",
        posicion=1,
        es_final=False,
    )
    dto_estado = EstadoOrdenResponse.model_validate(orm_estado)
    assert dto_estado.codigo == "PENDIENTE"
    assert dto_estado.posicion == 1
    assert dto_estado.es_final is False

    # 4. ItemOrdenDetalleResponse y OrdenTrabajoDetalleResponse
    now = datetime.now(timezone.utc)
    item_detalle = ItemOrdenDetalleResponse(
        repuesto_id=1,
        codigo="FIL-001",
        descripcion="Filtro de aceite",
        cantidad=2,
        precio_unitario=Decimal("8500.00"),
        subtotal=Decimal("17000.00"),
    )
    assert item_detalle.subtotal == Decimal("17000.00")

    historial_dto = HistorialEstadoOrdenResponse(
        desde_estado=None,
        hasta_estado="PENDIENTE",
        usuario_id=1,
        cuando=now,
    )

    orden_detalle = OrdenTrabajoDetalleResponse(
        id=5,
        estado="PENDIENTE",
        patente="AA123BB",
        total=Decimal("17000.00"),
        creada_en=now,
        mecanico_id=None,
        falla="Ruido al frenar",
        cliente="Laura Cliente",
        items=[item_detalle],
        historial=[historial_dto],
    )
    assert orden_detalle.id == 5
    assert orden_detalle.patente == "AA123BB"
    assert orden_detalle.cliente == "Laura Cliente"
    assert len(orden_detalle.items) == 1
    assert len(orden_detalle.historial) == 1

    # 5. OrdenTrabajoResumenResponse
    resumen = OrdenTrabajoResumenResponse(
        id=5,
        vehiculo_id=10,
        mecanico_id=None,
        estado="PENDIENTE",
        falla="Ruido",
        creada_en=now,
        total=Decimal("17000.00"),
    )
    assert resumen.id == 5


# ==============================================================================
# Tasks 1.2 & 1.3: Repositorios de Órdenes, Catálogo, Items, Historial y Eager Loading
# ==============================================================================

@pytest.mark.asyncio
async def test_ordenes_repositories_and_selectinload_c15() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.core.repository import BaseRepository, ReadOnlyRepository
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import EstadoOrden, HistorialEstadoOrden, ItemOrden, OrdenTrabajo
    from app.modules.ordenes.repository import (
        EstadoOrdenRepository,
        HistorialEstadoOrdenRepository,
        ItemOrdenRepository,
        OrdenTrabajoRepository,
    )
    from app.modules.repuestos.models import Repuesto
    from app.modules.usuarios.models import Usuario

    # 1. Verificación de jerarquía de clases (Regla de diseño RN-19 / Ejercicio 6)
    assert issubclass(EstadoOrdenRepository, ReadOnlyRepository)
    assert not issubclass(EstadoOrdenRepository, BaseRepository)
    assert issubclass(ItemOrdenRepository, BaseRepository)
    assert issubclass(HistorialEstadoOrdenRepository, BaseRepository)
    assert issubclass(OrdenTrabajoRepository, BaseRepository)

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        estado_repo = EstadoOrdenRepository(session)
        orden_repo = OrdenTrabajoRepository(session)
        item_repo = ItemOrdenRepository(session)
        hist_repo = HistorialEstadoOrdenRepository(session)

        # Cargar catálogo de estados si no existe
        for cod, desc, pos, fin in [
            ("PENDIENTE", "Pendiente", 1, False),
            ("EN_REPARACION", "En reparación", 2, False),
            ("TERMINADA", "Terminada", 3, True),
            ("CANCELADA", "Cancelada", 4, True),
        ]:
            existing = await estado_repo.get_by_pk(cod)
            if not existing:
                session.add(EstadoOrden(codigo=cod, descripcion=desc, posicion=pos, es_final=fin))
        await session.flush()

        estados = await estado_repo.list_ordered_by_posicion()
        assert len(estados) >= 4
        assert estados[0].codigo == "PENDIENTE"
        assert not await estado_repo.is_empty()

        # Crear entidades de prueba para la orden
        user = Usuario(email="cliente_orden_test@example.com", nombre="Cliente Test", password_hash="hash")
        mecanico = Usuario(email="mecanico_orden_test@example.com", nombre="Mecanico Test", password_hash="hash")
        session.add_all([user, mecanico])
        await session.flush()

        cliente = Cliente(usuario_id=user.id, nombre="Laura Cliente", documento="DOC-ORD-1", telefono="123")
        session.add(cliente)
        await session.flush()

        vehiculo = Vehiculo(cliente_id=cliente.id, patente="ORD123", marca="Ford", modelo="Focus", anio=2020)
        session.add(vehiculo)
        await session.flush()

        rep1 = Repuesto(codigo="REP-ORD-1", descripcion="Filtro", precio=Decimal("1000.00"), stock=10)
        rep2 = Repuesto(codigo="REP-ORD-2", descripcion="Bujia", precio=Decimal("2000.00"), stock=10)
        session.add_all([rep1, rep2])
        await session.flush()

        # Crear Orden 1 con 2 items
        orden = await orden_repo.add(
            OrdenTrabajo(
                vehiculo_id=vehiculo.id,
                estado="PENDIENTE",
                falla="Ruido de motor",
                total=Decimal("3000.00"),
            )
        )
        assert orden.id is not None

        item1 = await item_repo.add(ItemOrden(orden_id=orden.id, repuesto_id=rep1.id, cantidad=1, precio_unitario=Decimal("1000.00")))
        item2 = await item_repo.add(ItemOrden(orden_id=orden.id, repuesto_id=rep2.id, cantidad=1, precio_unitario=Decimal("2000.00")))
        hist = await hist_repo.add(HistorialEstadoOrden(orden_id=orden.id, desde_estado=None, hasta_estado="PENDIENTE", usuario_id=user.id))

        # Lectura con detalle (selectinload)
        detalle = await orden_repo.get_detalle(orden.id)
        assert detalle is not None
        assert detalle.vehiculo is not None
        assert detalle.vehiculo.cliente.nombre == "Laura Cliente"
        assert len(detalle.items) == 2
        assert detalle.items[0].repuesto.codigo in ("REP-ORD-1", "REP-ORD-2")
        assert len(detalle.historial) == 1
        assert detalle.historial[0].hasta_estado == "PENDIENTE"

        # Listado paginado y conteo de abiertas
        items_pag, total = await orden_repo.list_paginado(estado="PENDIENTE", limit=10)
        assert total >= 1
        assert any(o.id == orden.id for o in items_pag)

        open_count = await orden_repo.count_open_by_vehiculo_id(vehiculo.id, final_estados=["TERMINADA", "CANCELADA"])
        assert open_count == 1


# ==============================================================================
# Task 1.4: OrdenesUnitOfWork y Atomic Rollback
# ==============================================================================

@pytest.mark.asyncio
async def test_ordenes_unit_of_work_commit_and_atomic_rollback() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import OrdenTrabajo
    from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
    from app.modules.usuarios.models import Usuario

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Setup inicial de catalogo, cliente y vehiculo
    import uuid
    suffix = uuid.uuid4().hex[:8]
    async with session_factory() as session:
        from app.modules.ordenes.models import EstadoOrden
        for cod, desc, pos, fin in [
            ("PENDIENTE", "Pendiente", 1, False),
            ("EN_REPARACION", "En reparación", 2, False),
            ("TERMINADA", "Terminada", 3, True),
            ("CANCELADA", "Cancelada", 4, True),
        ]:
            existing = await session.get(EstadoOrden, cod)
            if not existing:
                session.add(EstadoOrden(codigo=cod, descripcion=desc, posicion=pos, es_final=fin))
        await session.flush()

        user = Usuario(email=f"uow_user_{suffix}@example.com", nombre="UoW User", password_hash="hash")
        session.add(user)
        await session.flush()
        cli = Cliente(usuario_id=user.id, nombre="UoW Cli", documento=f"DOC-UOW-{suffix}", telefono="123")
        session.add(cli)
        await session.flush()
        veh = Vehiculo(cliente_id=cli.id, patente=f"UW{suffix[:5].upper()}", marca="VW", modelo="Gol", anio=2015)
        session.add(veh)
        await session.commit()
        veh_id = veh.id

    # 2. Commit exitoso con OrdenesUnitOfWork
    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        async with uow:
            nueva_orden = await uow.ordenes.add(
                OrdenTrabajo(
                    vehiculo_id=veh_id,
                    estado="PENDIENTE",
                    falla="Falla UoW",
                    total=Decimal("0.00"),
                )
            )
            orden_id = nueva_orden.id

    # Verificar que persistio
    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        async with uow:
            orden_guardada = await uow.ordenes.get_by_id(orden_id)
            assert orden_guardada is not None
            assert orden_guardada.falla == "Falla UoW"

    # 3. Rollback automatico ante excepcion
    try:
        async with session_factory() as session:
            uow = OrdenesUnitOfWork(session)
            async with uow:
                await uow.ordenes.add(
                    OrdenTrabajo(
                        vehiculo_id=veh_id,
                        estado="PENDIENTE",
                        falla="Falla que fallara",
                        total=Decimal("0.00"),
                    )
                )
                raise RuntimeError("Simulated failure inside UoW")
    except RuntimeError:
        pass

    # Verificar que la orden no persistio (rollback completo)
    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        async with uow:
            ordenes, _ = await uow.ordenes.list_paginado(vehiculo_ids=[veh_id])
            assert not any(o.falla == "Falla que fallara" for o in ordenes)


# ==============================================================================
# Tasks 2.1 to 2.5: OrdenesService Domain Logic & Rules (RN-10, 11, 12, 13, 17, 19)
# ==============================================================================

@pytest.mark.asyncio
async def test_ordenes_service_crear_orden_rn10_rn19() -> None:
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import EstadoOrden
    from app.modules.ordenes.schemas import CrearOrdenRequest, ItemOrdenInput
    from app.modules.ordenes.service import OrdenesService
    from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
    from app.modules.repuestos.models import Repuesto
    from app.modules.usuarios.models import Usuario

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    import uuid
    suffix = uuid.uuid4().hex[:8]

    async with session_factory() as session:
        # Cargar catálogo de estados
        for cod, desc, pos, fin in [
            ("PENDIENTE", "Pendiente", 1, False),
            ("EN_REPARACION", "En reparación", 2, False),
            ("TERMINADA", "Terminada", 3, True),
            ("CANCELADA", "Cancelada", 4, True),
        ]:
            if not await session.get(EstadoOrden, cod):
                session.add(EstadoOrden(codigo=cod, descripcion=desc, posicion=pos, es_final=fin))
        await session.flush()

        # Crear entidades base
        user = Usuario(email=f"usr_srv_{suffix}@example.com", nombre="Cliente Srv", password_hash="hash")
        session.add(user)
        await session.flush()

        cli = Cliente(usuario_id=user.id, nombre="Cliente Srv", documento=f"DOC-SRV-{suffix}", telefono="123")
        session.add(cli)
        await session.flush()

        veh = Vehiculo(cliente_id=cli.id, patente=f"SV{suffix[:5].upper()}", marca="Peugeot", modelo="208", anio=2021)
        session.add(veh)
        await session.flush()

        rep1 = Repuesto(codigo=f"R1-{suffix}", descripcion="Pastillas", precio=Decimal("32000.00"), stock=10)
        rep2 = Repuesto(codigo=f"R2-{suffix}", descripcion="Aceite", precio=Decimal("12000.00"), stock=20)
        session.add_all([rep1, rep2])
        await session.commit()
        veh_id = veh.id
        rep1_id = rep1.id
        rep2_id = rep2.id
        user_id = user.id

    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        service = OrdenesService(uow)

        # 1. Crear orden exitosa con 2 repuestos
        req = CrearOrdenRequest(
            vehiculo_id=veh_id,
            falla="Ruido al frenar",
            items=[
                ItemOrdenInput(repuesto_id=rep1_id, cantidad=1),
                ItemOrdenInput(repuesto_id=rep2_id, cantidad=3),
            ],
        )
        res = await service.crear_orden(req, usuario_id=user_id)
        assert res.id is not None
        assert res.estado == "PENDIENTE"
        assert res.total == Decimal("68000.00")  # (32000 * 1) + (12000 * 3) = 68000
        assert res.patente == f"SV{suffix[:5].upper()}"
        assert res.cliente == "Cliente Srv"
        assert len(res.items) == 2
        assert len(res.historial) == 1
        assert res.historial[0].hasta_estado == "PENDIENTE"

        # 2. Rechazo ante vehiculo inexistente (409)
        with pytest.raises(HTTPException) as exc:
            await service.crear_orden(
                CrearOrdenRequest(vehiculo_id=999999, falla="X", items=[ItemOrdenInput(repuesto_id=rep1_id, cantidad=1)]),
                usuario_id=user_id,
            )
        assert exc.value.status_code == 409

        # 3. Rechazo ante repuesto inexistente (409)
        with pytest.raises(HTTPException) as exc:
            await service.crear_orden(
                CrearOrdenRequest(vehiculo_id=veh_id, falla="X", items=[ItemOrdenInput(repuesto_id=999999, cantidad=1)]),
                usuario_id=user_id,
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_ordenes_service_transiciones_iniciar_y_terminar_rn11_rn13_rn14() -> None:
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import EstadoOrden
    from app.modules.ordenes.schemas import CrearOrdenRequest, ItemOrdenInput
    from app.modules.ordenes.service import OrdenesService
    from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
    from app.modules.repuestos.models import Repuesto
    from app.modules.usuarios.models import Usuario

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    import uuid
    suffix = uuid.uuid4().hex[:8]

    async with session_factory() as session:
        for cod, desc, pos, fin in [
            ("PENDIENTE", "Pendiente", 1, False),
            ("EN_REPARACION", "En reparación", 2, False),
            ("TERMINADA", "Terminada", 3, True),
            ("CANCELADA", "Cancelada", 4, True),
        ]:
            if not await session.get(EstadoOrden, cod):
                session.add(EstadoOrden(codigo=cod, descripcion=desc, posicion=pos, es_final=fin))
        await session.flush()

        cli_user = Usuario(email=f"cli_{suffix}@example.com", nombre="Cli", password_hash="h")
        mec1 = Usuario(email=f"mec1_{suffix}@example.com", nombre="Mecanico 1", password_hash="h")
        mec2 = Usuario(email=f"mec2_{suffix}@example.com", nombre="Mecanico 2", password_hash="h")
        admin = Usuario(email=f"adm_{suffix}@example.com", nombre="Admin", password_hash="h")
        session.add_all([cli_user, mec1, mec2, admin])
        await session.flush()

        cli = Cliente(usuario_id=cli_user.id, nombre="Cli Auto", documento=f"DOC-T-{suffix}", telefono="444")
        session.add(cli)
        await session.flush()

        veh = Vehiculo(cliente_id=cli.id, patente=f"TR{suffix[:5].upper()}", marca="Fiat", modelo="Cronos", anio=2022)
        session.add(veh)
        await session.flush()

        rep = Repuesto(codigo=f"BUJ-{suffix}", descripcion="Bujia", precio=Decimal("5000.00"), stock=2)
        session.add(rep)
        await session.commit()
        veh_id = veh.id
        rep_id = rep.id
        mec1_id = mec1.id
        mec2_id = mec2.id
        admin_id = admin.id

    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        service = OrdenesService(uow)

        # Crear orden con 4 unidades cuando hay solo 2 en stock
        orden = await service.crear_orden(
            CrearOrdenRequest(vehiculo_id=veh_id, falla="Cambio de bujias", items=[ItemOrdenInput(repuesto_id=rep_id, cantidad=4)]),
            usuario_id=cli_user.id,
        )
        orden_id = orden.id

        # 1. Iniciar orden por mecanico 1
        # Falla si intenta alguien sin rol mecanico ni admin
        with pytest.raises(HTTPException) as exc:
            await service.iniciar_orden(orden_id=orden_id, mecanico_id=cli_user.id, roles=["CLIENTE"])
        assert exc.value.status_code == 403

        iniciada = await service.iniciar_orden(orden_id=orden_id, mecanico_id=mec1_id, roles=["MECANICO"])
        assert iniciada.estado == "EN_REPARACION"
        assert iniciada.mecanico_id == mec1_id
        assert len(iniciada.historial) == 2

        # Iniciar de nuevo da 409 (ya esta en reparacion)
        with pytest.raises(HTTPException) as exc:
            await service.iniciar_orden(orden_id=orden_id, mecanico_id=mec1_id, roles=["MECANICO"])
        assert exc.value.status_code == 409

        # 2. Terminar orden: Falla si intenta mecánico 2 no asignado (403)
        with pytest.raises(HTTPException) as exc:
            await service.terminar_orden(orden_id=orden_id, usuario_id=mec2_id, roles=["MECANICO"])
        assert exc.value.status_code == 403

        # 3. Terminar orden por mecanico 1 asignado pero CON STOCK INSUFICIENTE (pide 4 y hay 2) -> 409 y rollback total (RN-13)
        with pytest.raises(HTTPException) as exc:
            await service.terminar_orden(orden_id=orden_id, usuario_id=mec1_id, roles=["MECANICO"])
        assert exc.value.status_code == 409

    # Verificar que el stock no cambió y la orden sigue EN_REPARACION
    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        async with uow:
            r = await uow.repuestos.get_by_id(rep_id)
            assert r.stock == 2
            o = await uow.ordenes.get_by_id(orden_id)
            assert o.estado == "EN_REPARACION"

            # Reponer 10 bujias para que alcance el stock
            r.stock += 10
            await uow.repuestos.update(r)

    # 4. Ahora terminar con stock suficiente por admin_id -> 200, stock baja de 12 a 8, movimientos_stock se crea
    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        service = OrdenesService(uow)
        terminada = await service.terminar_orden(orden_id=orden_id, usuario_id=admin_id, roles=["ADMIN"])
        assert terminada.estado == "TERMINADA"
        assert len(terminada.historial) == 3

    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        async with uow:
            r = await uow.repuestos.get_by_id(rep_id)
            assert r.stock == 8
            movs = await uow.movimientos_stock.list_by_repuesto_id(rep_id)
            assert any(m.orden_id == orden_id and m.cantidad == -4 for m in movs)


@pytest.mark.asyncio
async def test_ordenes_service_cancelar_precedencia_rn12_y_aislamiento_rn17() -> None:
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import EstadoOrden
    from app.modules.ordenes.schemas import CrearOrdenRequest, ItemOrdenInput
    from app.modules.ordenes.service import OrdenesService
    from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
    from app.modules.repuestos.models import Repuesto
    from app.modules.usuarios.models import Usuario

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    import uuid
    suffix = uuid.uuid4().hex[:8]

    async with session_factory() as session:
        for cod, desc, pos, fin in [
            ("PENDIENTE", "Pendiente", 1, False),
            ("EN_REPARACION", "En reparación", 2, False),
            ("TERMINADA", "Terminada", 3, True),
            ("CANCELADA", "Cancelada", 4, True),
        ]:
            if not await session.get(EstadoOrden, cod):
                session.add(EstadoOrden(codigo=cod, descripcion=desc, posicion=pos, es_final=fin))
        await session.flush()

        u_laura = Usuario(email=f"laura_{suffix}@example.com", nombre="Laura", password_hash="h")
        u_juan = Usuario(email=f"juan_{suffix}@example.com", nombre="Juan", password_hash="h")
        u_recep = Usuario(email=f"recep_{suffix}@example.com", nombre="Recep", password_hash="h")
        session.add_all([u_laura, u_juan, u_recep])
        await session.flush()

        c_laura = Cliente(usuario_id=u_laura.id, nombre="Laura C", documento=f"DOC-L-{suffix}", telefono="111")
        c_juan = Cliente(usuario_id=u_juan.id, nombre="Juan C", documento=f"DOC-J-{suffix}", telefono="222")
        session.add_all([c_laura, c_juan])
        await session.flush()

        v_laura = Vehiculo(cliente_id=c_laura.id, patente=f"LA{suffix[:5].upper()}", marca="Ford", modelo="Ka", anio=2018)
        session.add(v_laura)
        await session.flush()

        rep = Repuesto(codigo=f"REP-C-{suffix}", descripcion="Foco", precio=Decimal("1000.00"), stock=10)
        session.add(rep)
        await session.commit()
        v_laura_id = v_laura.id
        rep_id = rep.id
        c_laura_id = c_laura.id
        c_juan_id = c_juan.id

    async with session_factory() as session:
        uow = OrdenesUnitOfWork(session)
        service = OrdenesService(uow)

        orden = await service.crear_orden(
            CrearOrdenRequest(vehiculo_id=v_laura_id, falla="Luz quemada", items=[ItemOrdenInput(repuesto_id=rep_id, cantidad=1)]),
            usuario_id=u_laura.id,
        )
        orden_id = orden.id

        # 1. Precedencia RN-12: Juan (cliente ajeno) intenta cancelar la orden de Laura
        # Debe recibir 403 Forbidden antes que comprobar cualquier estado (RN-12)
        with pytest.raises(HTTPException) as exc:
            await service.cancelar_orden(orden_id=orden_id, usuario_id=u_juan.id, roles=["CLIENTE"], cliente_id=c_juan_id)
        assert exc.value.status_code == 403

        # 2. Aislamiento RN-17: Juan intenta obtener el detalle de la orden de Laura -> 403
        with pytest.raises(HTTPException) as exc:
            await service.obtener_orden_detalle(orden_id=orden_id, usuario_id=u_juan.id, roles=["CLIENTE"], cliente_id=c_juan_id)
        assert exc.value.status_code == 403

        # 3. Laura sí puede ver su propia orden (200)
        detalle_laura = await service.obtener_orden_detalle(orden_id=orden_id, usuario_id=u_laura.id, roles=["CLIENTE"], cliente_id=c_laura_id)
        assert detalle_laura.id == orden_id

        # 4. Laura puede cancelar su orden pendiente (200)
        cancelada = await service.cancelar_orden(orden_id=orden_id, usuario_id=u_laura.id, roles=["CLIENTE"], cliente_id=c_laura_id)
        assert cancelada.estado == "CANCELADA"

        # 5. Intentar cancelar una orden ya cancelada por Laura -> 409 (porque Laura sí tiene permiso pero el estado ya no es PENDIENTE)
        with pytest.raises(HTTPException) as exc:
            await service.cancelar_orden(orden_id=orden_id, usuario_id=u_laura.id, roles=["CLIENTE"], cliente_id=c_laura_id)
        assert exc.value.status_code == 409



# ==============================================================================
# Task 3.1: Test de Corutina de Notificación Asincrónica en Segundo Plano
# ==============================================================================

@pytest.mark.asyncio
async def test_notificar_cliente_orden_terminada_coroutine(caplog: pytest.LogCaptureFixture) -> None:
    import logging
    import time
    from app.modules.ordenes.tasks import notificar_cliente_orden_terminada

    caplog.set_level(logging.INFO)
    start = time.perf_counter()
    await notificar_cliente_orden_terminada(orden_id=99, cliente_email="test_cliente")
    elapsed = time.perf_counter() - start

    assert elapsed >= 0.45
    assert any("Iniciando notificación" in record.message or "Aviso enviado" in record.message or "Notificación en segundo plano" in record.message for record in caplog.records)


# ==============================================================================
# Task 3.2 & 3.3: Tests de Integración HTTP de Endpoints de Órdenes y Lifecycle
# ==============================================================================

@pytest.mark.asyncio
async def test_ordenes_http_endpoints_full_lifecycle_and_security() -> None:
    from collections.abc import AsyncGenerator
    import uuid
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.core.database import get_session
    from app.core.dependencies import get_current_user
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import EstadoOrden
    from app.modules.repuestos.models import Repuesto
    from app.modules.usuarios.models import AsignacionRol, RolEnum, Usuario
    from main import app

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            for cod, desc, pos, fin in [
                ("PENDIENTE", "Pendiente", 1, False),
                ("EN_REPARACION", "En reparación", 2, False),
                ("TERMINADA", "Terminada", 3, True),
                ("CANCELADA", "Cancelada", 4, True),
            ]:
                if not await session.get(EstadoOrden, cod):
                    session.add(EstadoOrden(codigo=cod, descripcion=desc, posicion=pos, es_final=fin))
            await session.flush()

            u_admin = Usuario(email=f"admin_ord_{suffix}@test.com", nombre="Admin", password_hash="h", activo=True, debe_cambiar_password=False)
            u_recep = Usuario(email=f"recep_ord_{suffix}@test.com", nombre="Recep", password_hash="h", activo=True, debe_cambiar_password=False)
            u_mec1 = Usuario(email=f"mec1_ord_{suffix}@test.com", nombre="Mec1", password_hash="h", activo=True, debe_cambiar_password=False)
            u_mec2 = Usuario(email=f"mec2_ord_{suffix}@test.com", nombre="Mec2", password_hash="h", activo=True, debe_cambiar_password=False)
            u_cli1 = Usuario(email=f"cli1_ord_{suffix}@test.com", nombre="Cli1", password_hash="h", activo=True, debe_cambiar_password=False)
            u_cli2 = Usuario(email=f"cli2_ord_{suffix}@test.com", nombre="Cli2", password_hash="h", activo=True, debe_cambiar_password=False)
            u_pending = Usuario(email=f"pend_ord_{suffix}@test.com", nombre="Pend", password_hash="h", activo=True, debe_cambiar_password=True)

            session.add_all([u_admin, u_recep, u_mec1, u_mec2, u_cli1, u_cli2, u_pending])
            await session.flush()

            session.add_all([
                AsignacionRol(usuario_id=u_admin.id, rol=RolEnum.ADMIN),
                AsignacionRol(usuario_id=u_recep.id, rol=RolEnum.RECEPCION),
                AsignacionRol(usuario_id=u_mec1.id, rol=RolEnum.MECANICO),
                AsignacionRol(usuario_id=u_mec2.id, rol=RolEnum.MECANICO),
                AsignacionRol(usuario_id=u_cli1.id, rol=RolEnum.CLIENTE),
                AsignacionRol(usuario_id=u_cli2.id, rol=RolEnum.CLIENTE),
            ])
            await session.flush()

            c1 = Cliente(usuario_id=u_cli1.id, nombre="Cliente Uno", documento=f"D1-{suffix}", telefono="111")
            c2 = Cliente(usuario_id=u_cli2.id, nombre="Cliente Dos", documento=f"D2-{suffix}", telefono="222")
            session.add_all([c1, c2])
            await session.flush()

            v1 = Vehiculo(cliente_id=c1.id, patente=f"V1{suffix[:5].upper()}", marca="Toyota", modelo="Corolla", anio=2020)
            v2 = Vehiculo(cliente_id=c2.id, patente=f"V2{suffix[:5].upper()}", marca="VW", modelo="Golf", anio=2019)
            session.add_all([v1, v2])
            await session.flush()

            r1 = Repuesto(codigo=f"PAST-{suffix}", descripcion="Pastillas de freno", precio=Decimal("15000.00"), stock=5)
            r2 = Repuesto(codigo=f"DISC-{suffix}", descripcion="Disco de freno", precio=Decimal("25000.00"), stock=1)
            session.add_all([r1, r2])
            await session.commit()

            v1_id = v1.id
            r1_id = r1.id
            r2_id = r2.id

        current_actor: dict[str, Usuario] = {"user": u_admin}

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
            # 0. Petición sin token -> 401
            res_401 = await client.get("/estados-orden")
            assert res_401.status_code == 401

            # Configurar auth override
            app.dependency_overrides[get_current_user] = _override_current_user

            # 0b. Usuario con debe_cambiar_password=True bloqueado en router_protegido -> 403 (RN-06)
            current_actor["user"] = u_pending
            res_403_pwd = await client.get("/estados-orden")
            assert res_403_pwd.status_code == 403

            # 1. GET /estados-orden (200 OK ordenado por posicion)
            current_actor["user"] = u_admin
            res_estados = await client.get("/estados-orden")
            assert res_estados.status_code == 200
            estados_data = res_estados.json()
            assert len(estados_data) >= 4
            posiciones = [e["posicion"] for e in estados_data]
            assert posiciones == sorted(posiciones)

            # 2. POST /ordenes - Validaciones y Rechazos
            # 2a. Rol insuficiente: CLIENTE intenta crear orden -> 403
            current_actor["user"] = u_cli1
            res_cli_post = await client.post("/ordenes", json={"vehiculo_id": v1_id, "falla": "Frenos", "items": [{"repuesto_id": r1_id, "cantidad": 1}]})
            assert res_cli_post.status_code == 403

            # 2b. extra="forbid": intento de inyectar precio o total -> 422
            current_actor["user"] = u_recep
            res_extra = await client.post("/ordenes", json={"vehiculo_id": v1_id, "falla": "Frenos", "items": [{"repuesto_id": r1_id, "cantidad": 1}], "total": 1000})
            assert res_extra.status_code == 422

            # 2c. Items vacíos o repetidos -> 422
            res_empty_items = await client.post("/ordenes", json={"vehiculo_id": v1_id, "falla": "Frenos", "items": []})
            assert res_empty_items.status_code == 422

            res_dup_items = await client.post("/ordenes", json={"vehiculo_id": v1_id, "falla": "Frenos", "items": [{"repuesto_id": r1_id, "cantidad": 1}, {"repuesto_id": r1_id, "cantidad": 2}]})
            assert res_dup_items.status_code == 422

            # 2d. Vehículo o repuesto inexistente -> 409
            res_inexistente = await client.post("/ordenes", json={"vehiculo_id": 999999, "falla": "Frenos", "items": [{"repuesto_id": r1_id, "cantidad": 1}]})
            assert res_inexistente.status_code == 409

            # 2e. Creación exitosa por RECEPCION -> 201 Created
            res_crear = await client.post("/ordenes", json={
                "vehiculo_id": v1_id,
                "falla": "Vibración al frenar",
                "items": [
                    {"repuesto_id": r1_id, "cantidad": 2},
                    {"repuesto_id": r2_id, "cantidad": 1},
                ],
            })
            assert res_crear.status_code == 201
            orden_data = res_crear.json()
            orden_id = orden_data["id"]
            assert orden_data["estado"] == "PENDIENTE"
            assert Decimal(str(orden_data["total"])) == Decimal("55000.00")
            assert len(orden_data["items"]) == 2
            assert len(orden_data["historial"]) == 1
            assert orden_data["historial"][0]["desde_estado"] is None
            assert orden_data["historial"][0]["hasta_estado"] == "PENDIENTE"

            # 3. GET /ordenes (Listado y filtros con paginación)
            # 3a. CLIENTE no puede listar todas las ordenes -> 403
            current_actor["user"] = u_cli1
            res_list_cli = await client.get("/ordenes")
            assert res_list_cli.status_code == 403

            # 3b. RECEPCION lista con éxito
            current_actor["user"] = u_recep
            res_list_staff = await client.get("/ordenes?page=1&size=10")
            assert res_list_staff.status_code == 200
            pag_data = res_list_staff.json()
            assert "items" in pag_data
            assert pag_data["total"] >= 1
            assert any(item["id"] == orden_id for item in pag_data["items"])

            # 4. GET /ordenes/{id} (Aislamiento RN-17)
            # 4a. Cliente ajeno (u_cli2) intenta ver orden de c1 -> 403
            current_actor["user"] = u_cli2
            res_detalle_ajeno = await client.get(f"/ordenes/{orden_id}")
            assert res_detalle_ajeno.status_code == 403

            # 4b. Cliente dueño (u_cli1) consulta el detalle de su orden -> 200 OK
            current_actor["user"] = u_cli1
            res_detalle_propio = await client.get(f"/ordenes/{orden_id}")
            assert res_detalle_propio.status_code == 200
            assert res_detalle_propio.json()["id"] == orden_id

            # 4c. MECANICO consulta el detalle -> 200 OK
            current_actor["user"] = u_mec1
            res_detalle_mec = await client.get(f"/ordenes/{orden_id}")
            assert res_detalle_mec.status_code == 200

            # 5. POST /ordenes/{id}/iniciar (Máquina de estados RN-11)
            # 5a. RECEPCION intenta iniciar orden -> 403
            current_actor["user"] = u_recep
            res_iniciar_recep = await client.post(f"/ordenes/{orden_id}/iniciar")
            assert res_iniciar_recep.status_code == 403

            # 5b. MECANICO 1 inicia la orden -> 200 OK
            current_actor["user"] = u_mec1
            res_iniciar_mec1 = await client.post(f"/ordenes/{orden_id}/iniciar")
            assert res_iniciar_mec1.status_code == 200
            iniciada_data = res_iniciar_mec1.json()
            assert iniciada_data["estado"] == "EN_REPARACION"
            assert iniciada_data["mecanico_id"] == u_mec1.id
            assert len(iniciada_data["historial"]) == 2

            # 5c. Intentar iniciar nuevamente cuando ya está en reparación -> 409 Conflict
            res_iniciar_again = await client.post(f"/ordenes/{orden_id}/iniciar")
            assert res_iniciar_again.status_code == 409

            # 6. POST /ordenes/{id}/cancelar (Precedencia RN-12)
            # 6a. Cliente ajeno intenta cancelar la orden (ahora EN_REPARACION) -> 403 antes que 409
            current_actor["user"] = u_cli2
            res_cancel_ajeno = await client.post(f"/ordenes/{orden_id}/cancelar")
            assert res_cancel_ajeno.status_code == 403

            # 6b. Dueña intenta cancelar su orden cuando ya está EN_REPARACION -> 409
            current_actor["user"] = u_cli1
            res_cancel_invalido = await client.post(f"/ordenes/{orden_id}/cancelar")
            assert res_cancel_invalido.status_code == 409

            # 7. POST /ordenes/{id}/terminar (Descuento atómico RN-13 y BackgroundTasks)
            # 7a. Mecánico 2 (no asignado) intenta terminar la orden -> 403
            current_actor["user"] = u_mec2
            res_term_mec2 = await client.post(f"/ordenes/{orden_id}/terminar")
            assert res_term_mec2.status_code == 403

            # 7b. Mecánico 1 (asignado) termina la orden exitosamente -> 200 OK
            current_actor["user"] = u_mec1
            res_term_ok = await client.post(f"/ordenes/{orden_id}/terminar")
            assert res_term_ok.status_code == 200
            term_data = res_term_ok.json()
            assert term_data["estado"] == "TERMINADA"
            assert len(term_data["historial"]) == 3

            # 7c. Intentar terminar nuevamente cuando ya está terminada -> 409
            res_term_repetida = await client.post(f"/ordenes/{orden_id}/terminar")
            assert res_term_repetida.status_code == 409

            # 8. GET /mis-ordenes (Aislamiento RN-17)
            # 8a. Cliente 1 ve su orden en mis-ordenes -> 200 OK con items
            current_actor["user"] = u_cli1
            res_mis_ord_c1 = await client.get("/mis-ordenes")
            assert res_mis_ord_c1.status_code == 200
            mis_data_c1 = res_mis_ord_c1.json()
            assert mis_data_c1["total"] == 1
            assert mis_data_c1["items"][0]["id"] == orden_id

            # 8b. Cliente 2 consulta mis-ordenes -> 200 OK vacío (total == 0)
            current_actor["user"] = u_cli2
            res_mis_ord_c2 = await client.get("/mis-ordenes")
            assert res_mis_ord_c2.status_code == 200
            mis_data_c2 = res_mis_ord_c2.json()
            assert mis_data_c2["total"] == 0
            assert mis_data_c2["items"] == []

        app.dependency_overrides.clear()
        await trans.rollback()
