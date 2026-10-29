from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401


def test_repuestos_schemas_validation_extra_forbid_and_rn14() -> None:
    from app.modules.repuestos.models import (
        HistorialPrecioRepuesto,
        MovimientoStock,
        Repuesto,
    )
    from app.modules.repuestos.schemas import (
        ActualizarRepuestoRequest,
        CrearRepuestoRequest,
        HistorialPrecioResponse,
        MovimientoStockResponse,
        ReponerStockRequest,
        RepuestoResponse,
    )

    # 1. CrearRepuestoRequest válido (con stock_inicial explícito y por defecto 0)
    req_crear = CrearRepuestoRequest(
        codigo="  FIL-001  ",
        descripcion="  Filtro de aceite  ",
        precio=Decimal("8500.00"),
        stock_inicial=10,
    )
    assert req_crear.codigo == "FIL-001"
    assert req_crear.descripcion == "Filtro de aceite"
    assert req_crear.precio == Decimal("8500.00")
    assert req_crear.stock_inicial == 10

    req_crear_sin_stock = CrearRepuestoRequest(
        codigo="BUJ-002",
        descripcion="Bujía encendido",
        precio=Decimal("4200.50"),
    )
    assert req_crear_sin_stock.stock_inicial == 0

    # Rechazo por campo no declarado en CrearRepuestoRequest (Regla Dura #1: extra="forbid")
    with pytest.raises(ValidationError):
        CrearRepuestoRequest(
            codigo="FIL-001",
            descripcion="Filtro",
            precio=Decimal("100.00"),
            borrado_en=None,  # type: ignore[call-arg]
        )

    # Rechazo por precio <= 0 o stock_inicial < 0 o strings vacíos
    with pytest.raises(ValidationError):
        CrearRepuestoRequest(
            codigo="FIL-001",
            descripcion="Filtro",
            precio=Decimal("0.00"),
            stock_inicial=1,
        )

    with pytest.raises(ValidationError):
        CrearRepuestoRequest(
            codigo="FIL-001",
            descripcion="Filtro",
            precio=Decimal("-50.00"),
            stock_inicial=1,
        )

    with pytest.raises(ValidationError):
        CrearRepuestoRequest(
            codigo="FIL-001",
            descripcion="Filtro",
            precio=Decimal("100.00"),
            stock_inicial=-1,
        )

    with pytest.raises(ValidationError):
        CrearRepuestoRequest(
            codigo="   ",
            descripcion="Filtro",
            precio=Decimal("100.00"),
        )

    # 2. ActualizarRepuestoRequest parcial (Regla Dura #2: model_dump(exclude_unset=True))
    req_patch_desc = ActualizarRepuestoRequest(descripcion="  Filtro sintético  ")
    assert req_patch_desc.model_dump(exclude_unset=True) == {
        "descripcion": "Filtro sintético"
    }

    req_patch_precio = ActualizarRepuestoRequest(precio=Decimal("9200.00"))
    assert req_patch_precio.model_dump(exclude_unset=True) == {
        "precio": Decimal("9200.00")
    }

    # RN-14: prohibido enviar "stock" en ActualizarRepuestoRequest -> ValidationError
    with pytest.raises(ValidationError):
        ActualizarRepuestoRequest(
            descripcion="Intento cambiar stock",
            stock=99,  # type: ignore[call-arg]
        )

    # Rechazo de precio <= 0 o null explícito en campos enviados de PATCH
    with pytest.raises(ValidationError):
        ActualizarRepuestoRequest(precio=Decimal("0"))

    with pytest.raises(ValidationError):
        ActualizarRepuestoRequest.model_validate({"precio": None})

    with pytest.raises(ValidationError):
        ActualizarRepuestoRequest.model_validate({"descripcion": None})

    # 3. ReponerStockRequest válido e inválidos
    req_reponer = ReponerStockRequest(cantidad=5, motivo="  Compra a proveedor  ")
    assert req_reponer.cantidad == 5
    assert req_reponer.motivo == "Compra a proveedor"

    with pytest.raises(ValidationError):
        ReponerStockRequest(cantidad=0, motivo="Compra")

    with pytest.raises(ValidationError):
        ReponerStockRequest(cantidad=-3, motivo="Compra")

    with pytest.raises(ValidationError):
        ReponerStockRequest(cantidad=5, motivo="   ")

    with pytest.raises(ValidationError):
        ReponerStockRequest(
            cantidad=5,
            motivo="Compra",
            orden_id=1,  # type: ignore[call-arg]
        )

    # 4. Esquemas de salida con from_attributes=True
    now = datetime.now(timezone.utc)
    orm_repuesto = Repuesto(
        id=1,
        codigo="FIL-001",
        descripcion="Filtro de aceite",
        precio=Decimal("8500.00"),
        stock=10,
    )
    resp_rep = RepuestoResponse.model_validate(orm_repuesto)
    assert resp_rep.id == 1
    assert resp_rep.codigo == "FIL-001"
    assert resp_rep.precio == Decimal("8500.00")
    assert resp_rep.stock == 10

    orm_mov = MovimientoStock(
        id=10,
        repuesto_id=1,
        orden_id=None,
        usuario_id=2,
        cantidad=10,
        motivo="Stock inicial",
        cuando=now,
    )
    resp_mov = MovimientoStockResponse.model_validate(orm_mov)
    assert resp_mov.id == 10
    assert resp_mov.repuesto_id == 1
    assert resp_mov.orden_id is None
    assert resp_mov.usuario_id == 2
    assert resp_mov.cantidad == 10
    assert resp_mov.motivo == "Stock inicial"
    assert resp_mov.cuando == now

    orm_hist = HistorialPrecioRepuesto(
        id=20,
        repuesto_id=1,
        usuario_id=2,
        precio_anterior=Decimal("8000.00"),
        precio_nuevo=Decimal("8500.00"),
        cuando=now,
    )
    resp_hist = HistorialPrecioResponse.model_validate(orm_hist)
    assert resp_hist.id == 20
    assert resp_hist.repuesto_id == 1
    assert resp_hist.usuario_id == 2
    assert resp_hist.precio_anterior == Decimal("8000.00")
    assert resp_hist.precio_nuevo == Decimal("8500.00")
    assert resp_hist.cuando == now


@pytest.mark.asyncio
async def test_repuestos_repositories_uow_and_bound_param_search() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.core.unit_of_work import UnitOfWork
    from app.modules.repuestos.models import (
        HistorialPrecioRepuesto,
        MovimientoStock,
        Repuesto,
    )
    from app.modules.repuestos.repository import (
        HistorialPrecioRepuestoRepository,
        MovimientoStockRepository,
        RepuestoRepository,
    )
    from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork
    from app.modules.usuarios.models import Usuario

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # 1. Verificar exposición en UnitOfWork y RepuestosUnitOfWork
            uow = RepuestosUnitOfWork(session)
            assert isinstance(uow, UnitOfWork)
            async with uow as active_uow:
                assert isinstance(active_uow.repuestos, RepuestoRepository)
                assert isinstance(active_uow.movimientos_stock, MovimientoStockRepository)
                assert isinstance(
                    active_uow.historial_precios, HistorialPrecioRepuestoRepository
                )

            rep_repo = RepuestoRepository(session)
            mov_repo = MovimientoStockRepository(session)
            hist_repo = HistorialPrecioRepuestoRepository(session)

            admin = Usuario(
                email="admin_rep_repo@example.com",
                nombre="Admin Repo",
                password_hash="hash_test",
            )
            session.add(admin)
            await session.flush()
            assert admin.id is not None

            r1 = await rep_repo.add(
                Repuesto(
                    codigo="REP-REPO-01",
                    descripcion="Pastillas de freno delanteras",
                    precio=Decimal("32000.00"),
                    stock=4,
                )
            )
            r2 = await rep_repo.add(
                Repuesto(
                    codigo="REP-REPO-02",
                    descripcion="Disco de Freno ventilado",
                    precio=Decimal("45000.00"),
                    stock=2,
                )
            )
            r3_baja = await rep_repo.add(
                Repuesto(
                    codigo="REP-REPO-03",
                    descripcion="Líquido de freno DOT4",
                    precio=Decimal("9000.00"),
                    stock=0,
                    borrado_en=datetime.now(timezone.utc),
                )
            )
            r4_otro = await rep_repo.add(
                Repuesto(
                    codigo="REP-REPO-04",
                    descripcion="Filtro de aire motor",
                    precio=Decimal("11000.00"),
                    stock=8,
                )
            )
            assert (
                r1.id is not None
                and r2.id is not None
                and r3_baja.id is not None
                and r4_otro.id is not None
            )

            # 2. get_by_codigo (solo activos) y get_by_id_including_deleted (RN-16)
            found_r1 = await rep_repo.get_by_codigo("REP-REPO-01")
            assert found_r1 is not None and found_r1.id == r1.id
            assert await rep_repo.get_by_codigo("REP-REPO-03") is None
            assert await rep_repo.get_by_id(r3_baja.id) is None
            found_deleted = await rep_repo.get_by_id_including_deleted(r3_baja.id)
            assert found_deleted is not None and found_deleted.id == r3_baja.id

            # 3. search_active y count_active con ILIKE e inyección SQL (C-15 / C-16)
            frenos = await rep_repo.search_active(q="freno", offset=0, limit=10)
            total_frenos = await rep_repo.count_active(q="freno")
            freno_ids = [r.id for r in frenos]
            assert r1.id in freno_ids
            assert r2.id in freno_ids
            assert r3_baja.id not in freno_ids
            assert r4_otro.id not in freno_ids
            assert total_frenos >= 2

            # Intento de inyección SQL en q debe evaluarse como literal ligado -> 0 resultados
            sqli_items = await rep_repo.search_active(
                q="' OR '1'='1", offset=0, limit=10
            )
            sqli_total = await rep_repo.count_active(q="' OR '1'='1")
            assert sqli_items == []
            assert sqli_total == 0

            # 4. MovimientoStockRepository e HistorialPrecioRepuestoRepository ordenados por id.asc()
            m1 = await mov_repo.add(
                MovimientoStock(
                    repuesto_id=r1.id,
                    usuario_id=admin.id,
                    cantidad=4,
                    motivo="Stock inicial",
                )
            )
            m2 = await mov_repo.add(
                MovimientoStock(
                    repuesto_id=r1.id,
                    usuario_id=admin.id,
                    cantidad=6,
                    motivo="Reposición proveedor",
                )
            )
            movs = await mov_repo.list_by_repuesto_id(r1.id)
            assert [m.id for m in movs] == [m1.id, m2.id]

            h1 = await hist_repo.add(
                HistorialPrecioRepuesto(
                    repuesto_id=r1.id,
                    usuario_id=admin.id,
                    precio_anterior=Decimal("30000.00"),
                    precio_nuevo=Decimal("32000.00"),
                )
            )
            h2 = await hist_repo.add(
                HistorialPrecioRepuesto(
                    repuesto_id=r1.id,
                    usuario_id=admin.id,
                    precio_anterior=Decimal("32000.00"),
                    precio_nuevo=Decimal("35000.00"),
                )
            )
            precios = await hist_repo.list_by_repuesto_id(r1.id)
            assert [h.id for h in precios] == [h1.id, h2.id]

            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_append_only_triggers_reject_update_and_delete_c14_rn15() -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.modules.clientes.models import Cliente, Vehiculo
    from app.modules.ordenes.models import EstadoOrden, HistorialEstadoOrden, OrdenTrabajo
    from app.modules.repuestos.models import (
        HistorialPrecioRepuesto,
        MovimientoStock,
        Repuesto,
    )
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
                user = Usuario(
                    email="c14_trigger@example.com",
                    nombre="Trigger Tester",
                    password_hash="hash",
                )
                cli = Cliente(
                    nombre="Cliente C14",
                    documento="DOC-C14-001",
                    telefono="1100001414",
                )
                est = EstadoOrden(
                    codigo="PEND_C14",
                    descripcion="Pendiente C14",
                    posicion=914,
                    es_final=False,
                )
                rep = Repuesto(
                    codigo="REP-C14-01",
                    descripcion="Repuesto C14",
                    precio=Decimal("5000.00"),
                    stock=5,
                )
                session.add_all([user, cli, est, rep])
                await session.flush()
                assert user.id is not None and cli.id is not None and rep.id is not None

                veh = Vehiculo(
                    cliente_id=cli.id,
                    patente="C14PAT",
                    marca="Ford",
                    modelo="Fiesta",
                    anio=2020,
                )
                session.add(veh)
                await session.flush()
                assert veh.id is not None

                ot = OrdenTrabajo(
                    vehiculo_id=veh.id,
                    estado="PEND_C14",
                    falla="Falla C14",
                )
                session.add(ot)
                await session.flush()
                assert ot.id is not None

                mov = MovimientoStock(
                    repuesto_id=rep.id,
                    usuario_id=user.id,
                    cantidad=5,
                    motivo="Stock inicial C14",
                )
                hist_precio = HistorialPrecioRepuesto(
                    repuesto_id=rep.id,
                    usuario_id=user.id,
                    precio_anterior=Decimal("4500.00"),
                    precio_nuevo=Decimal("5000.00"),
                )
                hist_orden = HistorialEstadoOrden(
                    orden_id=ot.id,
                    desde_estado=None,
                    hasta_estado="PEND_C14",
                    usuario_id=user.id,
                )
                session.add_all([mov, hist_precio, hist_orden])
                await session.commit()
                assert (
                    mov.id is not None
                    and hist_precio.id is not None
                    and hist_orden.id is not None
                )

                # Caso C-14 (RN-15): UPDATE y DELETE deben ser rechazados por disparador en las 3 tablas
                casos_inmutables = [
                    (
                        "movimiento_stock",
                        "UPDATE movimiento_stock SET cantidad = 99 WHERE id = :id",
                        "DELETE FROM movimiento_stock WHERE id = :id",
                        mov.id,
                    ),
                    (
                        "historial_precio_repuesto",
                        "UPDATE historial_precio_repuesto SET precio_nuevo = 9999.00 WHERE id = :id",
                        "DELETE FROM historial_precio_repuesto WHERE id = :id",
                        hist_precio.id,
                    ),
                    (
                        "historial_estado_orden",
                        "UPDATE historial_estado_orden SET hasta_estado = 'PEND_C14' WHERE id = :id",
                        "DELETE FROM historial_estado_orden WHERE id = :id",
                        hist_orden.id,
                    ),
                ]

                for tabla, sql_update, sql_delete, row_id in casos_inmutables:
                    with pytest.raises(DBAPIError) as exc_upd:
                        async with session.begin_nested():
                            await session.execute(text(sql_update), {"id": row_id})
                    assert tabla in str(exc_upd.value)

                    with pytest.raises(DBAPIError) as exc_del:
                        async with session.begin_nested():
                            await session.execute(text(sql_delete), {"id": row_id})
                    assert tabla in str(exc_del.value)
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repuestos_service_create_reponer_soft_delete_and_rn01_rn14_rn16() -> None:
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.modules.repuestos.schemas import CrearRepuestoRequest, ReponerStockRequest
    from app.modules.repuestos.service import RepuestosService
    from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork
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
                admin = Usuario(
                    email="admin_svc_31@example.com",
                    nombre="Admin Svc 3.1",
                    password_hash="hash",
                )
                session.add(admin)
                await session.commit()
                assert admin.id is not None
                admin_id = admin.id

                uow = RepuestosUnitOfWork(session)
                service = RepuestosService(uow)

                # 1. Alta con stock_inicial > 0 crea repuesto y asiento "Stock inicial" (RN-14)
                r1 = await service.crear_repuesto(
                    CrearRepuestoRequest(
                        codigo="FIL-SVC-01",
                        descripcion="Filtro de aceite original",
                        precio=Decimal("8500.00"),
                        stock_inicial=10,
                    ),
                    usuario_id=admin_id,
                )
                assert r1.id is not None
                r1_id = r1.id
                assert r1.stock == 10
                assert r1.precio == Decimal("8500.00")

                movs_r1 = await uow.movimientos_stock.list_by_repuesto_id(r1_id)
                assert len(movs_r1) == 1
                assert movs_r1[0].cantidad == 10
                assert movs_r1[0].motivo == "Stock inicial"
                assert movs_r1[0].usuario_id == admin_id
                assert movs_r1[0].orden_id is None

                # 2. Alta con stock_inicial == 0 NO genera fila en movimiento_stock
                r2 = await service.crear_repuesto(
                    CrearRepuestoRequest(
                        codigo="BUJ-SVC-02",
                        descripcion="Bujía iridio",
                        precio=Decimal("12000.00"),
                        stock_inicial=0,
                    ),
                    usuario_id=admin_id,
                )
                assert r2.id is not None
                r2_id = r2.id
                assert r2.stock == 0
                movs_r2 = await uow.movimientos_stock.list_by_repuesto_id(r2_id)
                assert movs_r2 == []

                # 3. Código activo duplicado -> 409 Conflict (RN-01) sin detalles internos de BD
                with pytest.raises(HTTPException) as exc_dup:
                    await service.crear_repuesto(
                        CrearRepuestoRequest(
                            codigo="FIL-SVC-01",
                            descripcion="Filtro duplicado",
                            precio=Decimal("9000.00"),
                            stock_inicial=5,
                        ),
                        usuario_id=admin_id,
                    )
                assert exc_dup.value.status_code == 409
                assert "ix_repuesto_codigo_vigente" not in str(exc_dup.value.detail)

                # 4. Reposición manual incrementa stock y registra movimiento (RN-14)
                r1_rep = await service.reponer_stock(
                    r1_id,
                    ReponerStockRequest(cantidad=5, motivo="Compra a proveedor"),
                    usuario_id=admin_id,
                )
                assert r1_rep.stock == 15
                movs_r1_after = await uow.movimientos_stock.list_by_repuesto_id(r1_id)
                assert len(movs_r1_after) == 2
                assert movs_r1_after[1].cantidad == 5
                assert movs_r1_after[1].motivo == "Compra a proveedor"

                # 5. Punto único registrar_movimiento_stock rechaza cantidad == 0 (422) y saldo negativo (409)
                async with uow:
                    rep_loaded = await uow.repuestos.get_by_id(r1_id)
                    assert rep_loaded is not None
                    with pytest.raises(HTTPException) as exc_zero:
                        await service.registrar_movimiento_stock(
                            repuesto=rep_loaded,
                            cantidad=0,
                            motivo="Invalido cero",
                            usuario_id=admin_id,
                        )
                    assert exc_zero.value.status_code == 422

                    with pytest.raises(HTTPException) as exc_neg:
                        await service.registrar_movimiento_stock(
                            repuesto=rep_loaded,
                            cantidad=-999,
                            motivo="Consumo excesivo",
                            usuario_id=admin_id,
                        )
                    assert exc_neg.value.status_code == 409

                # 6. Baja lógica (RN-16) y reutilización de código dado de baja (RN-01)
                await service.eliminar_repuesto(r1_id)

                # Eliminar de nuevo o reponer sobre dado de baja -> 404
                with pytest.raises(HTTPException) as exc_del_again:
                    await service.eliminar_repuesto(r1_id)
                assert exc_del_again.value.status_code == 404

                with pytest.raises(HTTPException) as exc_rep_baja:
                    await service.reponer_stock(
                        r1_id,
                        ReponerStockRequest(cantidad=3, motivo="Compra post baja"),
                        usuario_id=admin_id,
                    )
                assert exc_rep_baja.value.status_code == 404

                # Reutilizar código "FIL-SVC-01" tras baja lógica -> 201 exitoso (RN-01)
                r1_nuevo = await service.crear_repuesto(
                    CrearRepuestoRequest(
                        codigo="FIL-SVC-01",
                        descripcion="Filtro de aceite nueva versión",
                        precio=Decimal("9500.00"),
                        stock_inicial=3,
                    ),
                    usuario_id=admin_id,
                )
                assert r1_nuevo.id is not None
                assert r1_nuevo.id != r1_id
                assert r1_nuevo.stock == 3
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repuestos_service_patch_rn20_pagination_and_history_after_soft_delete_rn16() -> None:
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.core.config import get_settings
    from app.core.paginacion import ParametrosPaginacion
    from app.modules.repuestos.schemas import (
        ActualizarRepuestoRequest,
        CrearRepuestoRequest,
    )
    from app.modules.repuestos.service import RepuestosService
    from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork
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
                admin = Usuario(
                    email="admin_svc_32@example.com",
                    nombre="Admin Svc 3.2",
                    password_hash="hash",
                )
                session.add(admin)
                await session.commit()
                assert admin.id is not None
                admin_id = admin.id

                uow = RepuestosUnitOfWork(session)
                service = RepuestosService(uow)

                rep = await service.crear_repuesto(
                    CrearRepuestoRequest(
                        codigo="PAS-SVC-01",
                        descripcion="Pastillas de freno cerámicas",
                        precio=Decimal("32000.00"),
                        stock_inicial=4,
                    ),
                    usuario_id=admin_id,
                )
                assert rep.id is not None
                rep_id = rep.id

                # 1. PATCH solo descripcion (exclude_unset=True) -> NO inserta historial de precio (RN-20)
                rep_desc = await service.actualizar_repuesto(
                    rep_id,
                    ActualizarRepuestoRequest(
                        descripcion="Pastillas de freno cerámicas premium"
                    ),
                    usuario_id=admin_id,
                )
                assert rep_desc.descripcion == "Pastillas de freno cerámicas premium"
                assert rep_desc.precio == Decimal("32000.00")
                assert await service.listar_precios(rep_id) == []

                # 2. PATCH con precio idéntico al actual -> NO inserta historial de precio (RN-20)
                rep_same = await service.actualizar_repuesto(
                    rep_id,
                    ActualizarRepuestoRequest(precio=Decimal("32000.00")),
                    usuario_id=admin_id,
                )
                assert rep_same.precio == Decimal("32000.00")
                assert await service.listar_precios(rep_id) == []

                # 3. PATCH con cambio efectivo de precio -> actualiza precio e inserta fila en historial (RN-20)
                rep_price = await service.actualizar_repuesto(
                    rep_id,
                    ActualizarRepuestoRequest(precio=Decimal("35500.00")),
                    usuario_id=admin_id,
                )
                assert rep_price.precio == Decimal("35500.00")
                assert (
                    rep_price.descripcion == "Pastillas de freno cerámicas premium"
                )
                hist_list = await service.listar_precios(rep_id)
                assert len(hist_list) == 1
                assert hist_list[0].precio_anterior == Decimal("32000.00")
                assert hist_list[0].precio_nuevo == Decimal("35500.00")
                assert hist_list[0].usuario_id == admin_id

                # 4. obtener_repuesto y listar_repuestos paginado con filtro q
                obtained = await service.obtener_repuesto(rep_id)
                assert obtained.id == rep_id

                page_1 = await service.listar_repuestos(
                    params=ParametrosPaginacion(page=1, size=10),
                    q="cerámicas",
                )
                assert page_1.total >= 1
                assert any(item.id == rep_id for item in page_1.items)

                # Página fuera de rango respecto al total filtrado -> 422
                with pytest.raises(HTTPException) as exc_page:
                    await service.listar_repuestos(
                        params=ParametrosPaginacion(page=99, size=10),
                        q="cerámicas",
                    )
                assert exc_page.value.status_code == 422

                # 5. Baja lógica oculta el repuesto de obtener_repuesto/listar_repuestos, pero conserva historiales (RN-16)
                await service.eliminar_repuesto(rep_id)

                with pytest.raises(HTTPException) as exc_get_del:
                    await service.obtener_repuesto(rep_id)
                assert exc_get_del.value.status_code == 404

                with pytest.raises(HTTPException) as exc_patch_del:
                    await service.actualizar_repuesto(
                        rep_id,
                        ActualizarRepuestoRequest(descripcion="No debería"),
                        usuario_id=admin_id,
                    )
                assert exc_patch_del.value.status_code == 404

                movs_post_baja = await service.listar_movimientos(rep_id)
                precios_post_baja = await service.listar_precios(rep_id)
                assert len(movs_post_baja) == 1
                assert len(precios_post_baja) == 1

                # ID que jamás existió -> 404 en listar_movimientos y listar_precios
                with pytest.raises(HTTPException) as exc_mov_404:
                    await service.listar_movimientos(999999)
                assert exc_mov_404.value.status_code == 404

                with pytest.raises(HTTPException) as exc_pre_404:
                    await service.listar_precios(999999)
                assert exc_pre_404.value.status_code == 404
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repuestos_http_endpoints_c15_c16_rbac_and_errors() -> None:
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
                    email="admin_rep_http@example.com",
                    nombre="Admin Rep HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                recep_user = Usuario(
                    email="recep_rep_http@example.com",
                    nombre="Recep Rep HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                mec_user = Usuario(
                    email="mec_rep_http@example.com",
                    nombre="Mec Rep HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                cli_user = Usuario(
                    email="cli_rep_http@example.com",
                    nombre="Cli Rep HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=False,
                )
                pending_user = Usuario(
                    email="pending_rep_http@example.com",
                    nombre="Pending Rep HTTP",
                    password_hash="hash",
                    activo=True,
                    debe_cambiar_password=True,
                )
                session.add_all(
                    [admin_user, recep_user, mec_user, cli_user, pending_user]
                )
                await session.flush()
                assert (
                    admin_user.id is not None
                    and recep_user.id is not None
                    and mec_user.id is not None
                    and cli_user.id is not None
                )

                session.add_all(
                    [
                        AsignacionRol(usuario_id=admin_user.id, rol=RolEnum.ADMIN),
                        AsignacionRol(usuario_id=recep_user.id, rol=RolEnum.RECEPCION),
                        AsignacionRol(usuario_id=mec_user.id, rol=RolEnum.MECANICO),
                        AsignacionRol(usuario_id=cli_user.id, rol=RolEnum.CLIENTE),
                    ]
                )
                await session.commit()

                current_actor: dict[str, Usuario] = {"user": admin_user}

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
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    # 0. Petición sin cookie access_token -> 401
                    res_401 = await client.get("/repuestos")
                    assert res_401.status_code == 401

                    # Activar override de usuario autenticado
                    app.dependency_overrides[get_current_user] = _override_current_user

                    # 0b. Usuario con debe_cambiar_password=True bloqueado en grupo protegido -> 403 (RN-06)
                    current_actor["user"] = pending_user
                    res_403_pwd = await client.get("/repuestos")
                    assert res_403_pwd.status_code == 403

                    # 0c. Usuario CLIENTE no puede siquiera listar /repuestos -> 403
                    current_actor["user"] = cli_user
                    assert (await client.get("/repuestos")).status_code == 403

                    # 1. Caso C-15: ADMIN crea repuestos (con stock_inicial > 0 y stock_inicial == 0)
                    current_actor["user"] = admin_user
                    res_create_1 = await client.post(
                        "/repuestos",
                        json={
                            "codigo": "FIL-HTTP-01",
                            "descripcion": "Filtro de aceite motor",
                            "precio": "8500.00",
                            "stock_inicial": 10,
                        },
                    )
                    assert res_create_1.status_code == 201
                    r1_data = res_create_1.json()
                    r1_id = r1_data["id"]
                    assert r1_data["codigo"] == "FIL-HTTP-01"
                    assert r1_data["stock"] == 10
                    assert Decimal(str(r1_data["precio"])) == Decimal("8500.00")

                    res_create_2 = await client.post(
                        "/repuestos",
                        json={
                            "codigo": "PAS-HTTP-02",
                            "descripcion": "Pastillas de freno delanteras",
                            "precio": "32000.00",
                            "stock_inicial": 0,
                        },
                    )
                    assert res_create_2.status_code == 201
                    r2_data = res_create_2.json()
                    r2_id = r2_data["id"]
                    assert r2_data["stock"] == 0

                    # Código activo duplicado -> 409 (RN-01)
                    res_dup = await client.post(
                        "/repuestos",
                        json={
                            "codigo": "FIL-HTTP-01",
                            "descripcion": "Otro filtro",
                            "precio": "9000.00",
                            "stock_inicial": 2,
                        },
                    )
                    assert res_dup.status_code == 409

                    # stock_inicial == 0 no genera movimientos; stock_inicial == 10 genera 1 movimiento
                    res_movs_r2 = await client.get(f"/repuestos/{r2_id}/movimientos")
                    assert res_movs_r2.status_code == 200
                    assert res_movs_r2.json() == []

                    # 2. Reposición manual POST /repuestos/{id}/reponer (200, 404, 422)
                    res_rep = await client.post(
                        f"/repuestos/{r1_id}/reponer",
                        json={"cantidad": 5, "motivo": "Compra a proveedor"},
                    )
                    assert res_rep.status_code == 200
                    assert res_rep.json()["stock"] == 15

                    res_rep_422 = await client.post(
                        f"/repuestos/{r1_id}/reponer",
                        json={"cantidad": 0, "motivo": "Invalido"},
                    )
                    assert res_rep_422.status_code == 422

                    res_rep_404 = await client.post(
                        "/repuestos/999999/reponer",
                        json={"cantidad": 5, "motivo": "No existe"},
                    )
                    assert res_rep_404.status_code == 404

                    # Verificar movimientos de r1 (Stock inicial + Compra a proveedor)
                    res_movs_r1 = await client.get(f"/repuestos/{r1_id}/movimientos")
                    assert res_movs_r1.status_code == 200
                    movs_r1 = res_movs_r1.json()
                    assert len(movs_r1) == 2
                    assert movs_r1[0]["cantidad"] == 10
                    assert movs_r1[0]["motivo"] == "Stock inicial"
                    assert movs_r1[1]["cantidad"] == 5
                    assert movs_r1[1]["motivo"] == "Compra a proveedor"

                    # 3. Caso C-15 y C-16: PATCH /repuestos/{id}
                    # Intentar enviar "stock" en PATCH -> 422 (RN-14)
                    res_patch_stock = await client.patch(
                        f"/repuestos/{r1_id}",
                        json={"stock": 999},
                    )
                    assert res_patch_stock.status_code == 422

                    # Enviar null explícito en precio o descripcion -> 422
                    assert (
                        await client.patch(
                            f"/repuestos/{r1_id}", json={"precio": None}
                        )
                    ).status_code == 422

                    # PATCH solo descripcion -> 200 OK y NO genera fila en historial_precio_repuesto (RN-20)
                    res_patch_desc = await client.patch(
                        f"/repuestos/{r1_id}",
                        json={"descripcion": "Filtro de aceite sintético"},
                    )
                    assert res_patch_desc.status_code == 200
                    assert (
                        res_patch_desc.json()["descripcion"]
                        == "Filtro de aceite sintético"
                    )
                    assert Decimal(str(res_patch_desc.json()["precio"])) == Decimal(
                        "8500.00"
                    )
                    assert (
                        await client.get(f"/repuestos/{r1_id}/precios")
                    ).json() == []

                    # PATCH mismo precio vigente -> 200 OK y NO genera fila en historial_precio_repuesto (RN-20)
                    res_patch_same = await client.patch(
                        f"/repuestos/{r1_id}",
                        json={"precio": "8500.00"},
                    )
                    assert res_patch_same.status_code == 200
                    assert (
                        await client.get(f"/repuestos/{r1_id}/precios")
                    ).json() == []

                    # PATCH cambio efectivo de precio -> 200 OK y genera 1 fila en historial_precio_repuesto (RN-20)
                    res_patch_price = await client.patch(
                        f"/repuestos/{r1_id}",
                        json={"precio": "9200.00"},
                    )
                    assert res_patch_price.status_code == 200
                    assert Decimal(str(res_patch_price.json()["precio"])) == Decimal(
                        "9200.00"
                    )

                    res_precios_r1 = await client.get(f"/repuestos/{r1_id}/precios")
                    assert res_precios_r1.status_code == 200
                    precios_r1 = res_precios_r1.json()
                    assert len(precios_r1) == 1
                    assert Decimal(str(precios_r1[0]["precio_anterior"])) == Decimal(
                        "8500.00"
                    )
                    assert Decimal(str(precios_r1[0]["precio_nuevo"])) == Decimal(
                        "9200.00"
                    )

                    # 4. Búsqueda paginada GET /repuestos y GET /repuestos/{id} para RECEPCION y MECANICO
                    for staff_user in (recep_user, mec_user):
                        current_actor["user"] = staff_user
                        res_list = await client.get(
                            "/repuestos", params={"q": "freno", "page": 1, "size": 2}
                        )
                        assert res_list.status_code == 200
                        list_body = res_list.json()
                        assert list_body["total"] == 1
                        assert list_body["pages"] == 1
                        assert len(list_body["items"]) == 1
                        assert list_body["items"][0]["id"] == r2_id

                        # Prevención de inyección SQL en q
                        res_sqli = await client.get(
                            "/repuestos", params={"q": "' OR '1'='1"}
                        )
                        assert res_sqli.status_code == 200
                        sqli_body = res_sqli.json()
                        assert sqli_body["items"] == []
                        assert sqli_body["total"] == 0
                        assert sqli_body["pages"] == 1

                        # Página fuera de rango respecto al total filtrado -> 422
                        res_oob = await client.get(
                            "/repuestos", params={"q": "freno", "page": 2, "size": 10}
                        )
                        assert res_oob.status_code == 422

                        # Detalle individual activo -> 200
                        res_det = await client.get(f"/repuestos/{r1_id}")
                        assert res_det.status_code == 200
                        assert res_det.json()["id"] == r1_id

                        # Operaciones exclusivas de ADMIN deben responder 403 para RECEPCION y MECANICO
                        assert (
                            await client.post(
                                "/repuestos",
                                json={
                                    "codigo": "NOPE",
                                    "descripcion": "Nope",
                                    "precio": "100.00",
                                    "stock_inicial": 1,
                                },
                            )
                        ).status_code == 403
                        assert (
                            await client.patch(
                                f"/repuestos/{r1_id}",
                                json={"descripcion": "Nope"},
                            )
                        ).status_code == 403
                        assert (
                            await client.delete(f"/repuestos/{r1_id}")
                        ).status_code == 403
                        assert (
                            await client.post(
                                f"/repuestos/{r1_id}/reponer",
                                json={"cantidad": 1, "motivo": "Nope"},
                            )
                        ).status_code == 403
                        assert (
                            await client.get(f"/repuestos/{r1_id}/movimientos")
                        ).status_code == 403
                        assert (
                            await client.get(f"/repuestos/{r1_id}/precios")
                        ).status_code == 403

                    # 5. Baja lógica DELETE /repuestos/{id}, reutilización de código (RN-01) y conservación de historiales (RN-16)
                    current_actor["user"] = admin_user
                    res_del = await client.delete(f"/repuestos/{r1_id}")
                    assert res_del.status_code == 204

                    # Ya no aparece en GET /repuestos/{id} (404) ni se puede eliminar de nuevo (404)
                    assert (await client.get(f"/repuestos/{r1_id}")).status_code == 404
                    assert (
                        await client.delete(f"/repuestos/{r1_id}")
                    ).status_code == 404

                    # Pero sus historiales siguen siendo consultables por ADMIN (RN-16 -> 200 OK)
                    assert (
                        await client.get(f"/repuestos/{r1_id}/movimientos")
                    ).status_code == 200
                    assert (
                        await client.get(f"/repuestos/{r1_id}/precios")
                    ).status_code == 200

                    # Historiales de un ID inexistente -> 404
                    assert (
                        await client.get("/repuestos/999999/movimientos")
                    ).status_code == 404
                    assert (
                        await client.get("/repuestos/999999/precios")
                    ).status_code == 404

                    # Reutilizar el código "FIL-HTTP-01" dado de baja -> 201 Created (RN-01)
                    res_reuse = await client.post(
                        "/repuestos",
                        json={
                            "codigo": "FIL-HTTP-01",
                            "descripcion": "Filtro de aceite reingresado",
                            "precio": "9800.00",
                            "stock_inicial": 6,
                        },
                    )
                    assert res_reuse.status_code == 201
                    assert res_reuse.json()["id"] != r1_id
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()

