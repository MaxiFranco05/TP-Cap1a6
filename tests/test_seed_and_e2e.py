from decimal import Decimal
import bcrypt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, HistorialEstadoOrden, ItemOrden, OrdenTrabajo
from app.modules.repuestos.models import HistorialPrecioRepuesto, MovimientoStock, Repuesto
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario


@pytest.mark.asyncio
async def test_seed_database_execution_and_content() -> None:
    """Verifica que seed.py pueble de forma exhaustiva y canónica todas las tablas del taller."""
    from seed import seed_database

    # Ejecutar la siembra canónica
    await seed_database()

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # 1. Catálogo de estados
        estados = (await session.execute(select(EstadoOrden).order_by(EstadoOrden.posicion))).scalars().all()
        assert len(estados) == 4
        codigos = [e.codigo for e in estados]
        assert codigos == ["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]
        assert [e.posicion for e in estados] == [1, 2, 3, 4]
        assert [e.es_final for e in estados] == [False, False, True, True]

        # 2. Usuarios y roles
        usuarios = (await session.execute(select(Usuario).order_by(Usuario.id))).scalars().all()
        assert len(usuarios) == 7
        user_by_email = {u.email: u for u in usuarios}

        expected_emails = [
            "admin@example.com",
            "admin2@example.com",
            "recepcion@example.com",
            "mecanico@example.com",
            "mecanico2@example.com",
            "cliente@example.com",
            "nuevo@example.com",
        ]
        for em in expected_emails:
            assert em in user_by_email
            # Comprobar que la contraseña es "Password123!"
            assert bcrypt.checkpw(b"Password123!", user_by_email[em].password_hash.encode("utf-8"))

        assert user_by_email["nuevo@example.com"].debe_cambiar_password is True
        assert user_by_email["admin@example.com"].debe_cambiar_password is False

        # Roles asignados
        roles = (await session.execute(select(AsignacionRol))).scalars().all()
        roles_by_user = {}
        for r in roles:
            roles_by_user.setdefault(r.usuario_id, []).append(r.rol)

        assert "ADMIN" in roles_by_user[user_by_email["admin@example.com"].id]
        assert "ADMIN" in roles_by_user[user_by_email["admin2@example.com"].id]
        assert "RECEPCION" in roles_by_user[user_by_email["recepcion@example.com"].id]
        assert "MECANICO" in roles_by_user[user_by_email["mecanico@example.com"].id]
        assert "MECANICO" in roles_by_user[user_by_email["mecanico2@example.com"].id]
        assert "CLIENTE" in roles_by_user[user_by_email["cliente@example.com"].id]
        assert "MECANICO" in roles_by_user[user_by_email["nuevo@example.com"].id]

        # 3. Clientes y vehículos
        clientes = (await session.execute(select(Cliente))).scalars().all()
        assert len(clientes) == 2
        cli_by_name = {c.nombre: c for c in clientes}
        assert "Laura" in cli_by_name
        assert "Jorge" in cli_by_name

        laura = cli_by_name["Laura"]
        jorge = cli_by_name["Jorge"]
        assert laura.usuario_id == user_by_email["cliente@example.com"].id
        assert jorge.usuario_id is None

        vehiculos_laura = (
            await session.execute(select(Vehiculo).where(Vehiculo.cliente_id == laura.id))
        ).scalars().all()
        assert len(vehiculos_laura) == 2
        assert any(v.patente == "AC456EF" for v in vehiculos_laura)

        vehiculos_jorge = (
            await session.execute(select(Vehiculo).where(Vehiculo.cliente_id == jorge.id))
        ).scalars().all()
        assert len(vehiculos_jorge) == 1

        # 4. Repuestos, stock y movimientos
        repuestos = (await session.execute(select(Repuesto))).scalars().all()
        assert len(repuestos) >= 4
        rep_by_desc = {r.descripcion: r for r in repuestos}

        assert "Filtro de aceite" in rep_by_desc
        assert rep_by_desc["Filtro de aceite"].precio == Decimal("8500.00")
        assert rep_by_desc["Filtro de aceite"].stock == 10

        assert "Pastillas de freno" in rep_by_desc
        assert rep_by_desc["Pastillas de freno"].precio == Decimal("32000.00")
        assert rep_by_desc["Pastillas de freno"].stock == 4

        assert "Bujía" in rep_by_desc
        assert rep_by_desc["Bujía"].stock == 2

        assert "Aceite por litro" in rep_by_desc
        assert rep_by_desc["Aceite por litro"].precio == Decimal("12000.00")
        assert rep_by_desc["Aceite por litro"].stock == 20

        # Movimientos de stock iniciales
        movs = (await session.execute(select(MovimientoStock))).scalars().all()
        assert len(movs) >= 4
        assert any("Stock inicial" in m.motivo and m.cantidad > 0 for m in movs)

        # Historial de precio del filtro
        hist_precios = (
            await session.execute(
                select(HistorialPrecioRepuesto).where(
                    HistorialPrecioRepuesto.repuesto_id == rep_by_desc["Filtro de aceite"].id
                )
            )
        ).scalars().all()
        assert len(hist_precios) >= 1
        assert hist_precios[0].precio_anterior == Decimal("8000.00")
        assert hist_precios[0].precio_nuevo == Decimal("8500.00")

        # Evento de seguridad inicial
        eventos = (await session.execute(select(EventoSeguridad))).scalars().all()
        assert len(eventos) >= 1
        assert any(e.actor == "SISTEMA" and "Carga de los datos iniciales" in e.accion for e in eventos)

        # 5. Órdenes de trabajo
        ordenes = (await session.execute(select(OrdenTrabajo).order_by(OrdenTrabajo.id))).scalars().all()
        assert len(ordenes) == 2

        ord1 = ordenes[0]
        assert ord1.estado == "PENDIENTE"
        assert ord1.vehiculo_id in [v.id for v in vehiculos_laura]
        assert ord1.total > Decimal("0")

        ord2 = ordenes[1]
        assert ord2.estado == "EN_REPARACION"
        assert ord2.vehiculo_id in [v.id for v in vehiculos_jorge]
        assert ord2.mecanico_id == user_by_email["mecanico@example.com"].id

        # Items de la orden 2 piden 4 bujías
        items_ord2 = (
            await session.execute(select(ItemOrden).where(ItemOrden.orden_id == ord2.id))
        ).scalars().all()
        assert any(it.repuesto_id == rep_by_desc["Bujía"].id and it.cantidad == 4 for it in items_ord2)

        # Historial de estados
        hist1 = (
            await session.execute(select(HistorialEstadoOrden).where(HistorialEstadoOrden.orden_id == ord1.id))
        ).scalars().all()
        assert len(hist1) == 1
        assert hist1[0].hasta_estado == "PENDIENTE"

        hist2 = (
            await session.execute(select(HistorialEstadoOrden).where(HistorialEstadoOrden.orden_id == ord2.id))
        ).scalars().all()
        assert len(hist2) == 2


@pytest.mark.asyncio
async def test_seed_database_idempotency() -> None:
    """Verifica que ejecutar seed.py dos veces consecutivas sea completamente idempotente."""
    from seed import seed_database

    await seed_database()
    await seed_database()

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        usuarios = (await session.execute(select(Usuario))).scalars().all()
        assert len(usuarios) == 7

        estados = (await session.execute(select(EstadoOrden))).scalars().all()
        assert len(estados) == 4

        ordenes = (await session.execute(select(OrdenTrabajo))).scalars().all()
        assert len(ordenes) == 2
