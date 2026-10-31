"""Script canónico e idempotente de carga inicial de datos (seed.py).

Puebla el catálogo de estados, usuarios de prueba con contraseñas seguras (bcrypt),
roles vigentes, clientes, vehículos, repuestos con stock inicial y movimientos,
historial de precios, auditoría y órdenes de trabajo canónicas (C-01 a C-19).
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import logging
import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, HistorialEstadoOrden, ItemOrden, OrdenTrabajo
from app.modules.repuestos.models import HistorialPrecioRepuesto, MovimientoStock, Repuesto
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, RolEnum, Usuario

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")


async def seed_database() -> None:
    """Limpia y repuebla de forma determinística e idempotente la base de datos."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("Iniciando limpieza de tablas con TRUNCATE ... RESTART IDENTITY CASCADE...")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                TRUNCATE TABLE
                    historial_estado_orden,
                    item_orden,
                    orden_trabajo,
                    movimiento_stock,
                    historial_precio_repuesto,
                    repuesto,
                    vehiculo,
                    cliente,
                    asignacion_rol,
                    intento_acceso,
                    evento_seguridad,
                    usuario,
                    estado_orden
                RESTART IDENTITY CASCADE;
                """
            )
        )
    logger.info("Tablas limpias y secuencias autonuméricas reiniciadas.")

    # Precalcular hash seguro para "Password123!" fuera del event loop
    salt = await asyncio.to_thread(bcrypt.gensalt, settings.BCRYPT_ROUNDS)
    pwd_bytes = await asyncio.to_thread(bcrypt.hashpw, b"Password123!", salt)
    password_hash = pwd_bytes.decode("utf-8")

    async with session_factory() as session:
        # 1. Catálogo inmutable de estados de orden (RN-19)
        estados = [
            EstadoOrden(
                codigo="PENDIENTE",
                descripcion="Orden creada pendiente de asignación",
                posicion=1,
                es_final=False,
            ),
            EstadoOrden(
                codigo="EN_REPARACION",
                descripcion="Orden en curso de reparación por mecánico asignado",
                posicion=2,
                es_final=False,
            ),
            EstadoOrden(
                codigo="TERMINADA",
                descripcion="Reparación finalizada exitosamente",
                posicion=3,
                es_final=True,
            ),
            EstadoOrden(
                codigo="CANCELADA",
                descripcion="Orden de trabajo cancelada",
                posicion=4,
                es_final=True,
            ),
        ]
        session.add_all(estados)
        await session.flush()
        logger.info("Catálogo de 4 estados insertado.")

        # 2. Usuarios canónicos de prueba
        usuarios = [
            Usuario(
                email="admin@example.com",
                nombre="Administrador Principal",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            ),
            Usuario(
                email="admin2@example.com",
                nombre="Administrador Secundario",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            ),
            Usuario(
                email="recepcion@example.com",
                nombre="Recepcionista Taller",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            ),
            Usuario(
                email="mecanico@example.com",
                nombre="Mecánico Titular",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            ),
            Usuario(
                email="mecanico2@example.com",
                nombre="Mecánico Auxiliar",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            ),
            Usuario(
                email="cliente@example.com",
                nombre="Laura González",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            ),
            Usuario(
                email="nuevo@example.com",
                nombre="Mecánico Nuevo (Pendiente Clave)",
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=True,
            ),
        ]
        session.add_all(usuarios)
        await session.flush()

        u_admin = usuarios[0]
        u_admin2 = usuarios[1]
        u_recep = usuarios[2]
        u_mec = usuarios[3]
        u_mec2 = usuarios[4]
        u_cli = usuarios[5]
        u_nuevo = usuarios[6]

        assert u_admin.id is not None
        assert u_admin2.id is not None
        assert u_recep.id is not None
        assert u_mec.id is not None
        assert u_mec2.id is not None
        assert u_cli.id is not None
        assert u_nuevo.id is not None

        # Asignaciones de roles vigentes (RN-03, RN-04)
        roles = [
            AsignacionRol(usuario_id=u_admin.id, rol=RolEnum.ADMIN),
            AsignacionRol(usuario_id=u_admin2.id, rol=RolEnum.ADMIN),
            AsignacionRol(usuario_id=u_recep.id, rol=RolEnum.RECEPCION),
            AsignacionRol(usuario_id=u_mec.id, rol=RolEnum.MECANICO),
            AsignacionRol(usuario_id=u_mec2.id, rol=RolEnum.MECANICO),
            AsignacionRol(usuario_id=u_cli.id, rol=RolEnum.CLIENTE),
            AsignacionRol(usuario_id=u_nuevo.id, rol=RolEnum.MECANICO),
        ]
        session.add_all(roles)
        await session.flush()
        logger.info("7 usuarios canónicos y sus roles asignados.")

        # 3. Clientes y vehículos (RN-02)
        cliente_laura = Cliente(
            nombre="Laura",
            documento="27123456",
            telefono="1145678901",
            usuario_id=u_cli.id,
        )
        cliente_jorge = Cliente(
            nombre="Jorge",
            documento="18456789",
            telefono="1156781234",
            usuario_id=None,
        )
        session.add_all([cliente_laura, cliente_jorge])
        await session.flush()

        assert cliente_laura.id is not None
        assert cliente_jorge.id is not None

        v_laura1 = Vehiculo(
            cliente_id=cliente_laura.id,
            patente="AC456EF",
            marca="Toyota",
            modelo="Corolla",
            anio=2020,
        )
        v_laura2 = Vehiculo(
            cliente_id=cliente_laura.id,
            patente="AD789GH",
            marca="Ford",
            modelo="Fiesta",
            anio=2018,
        )
        v_jorge = Vehiculo(
            cliente_id=cliente_jorge.id,
            patente="AE123IJ",
            marca="Volkswagen",
            modelo="Gol",
            anio=2015,
        )
        session.add_all([v_laura1, v_laura2, v_jorge])
        await session.flush()
        logger.info("Clientes Laura (2 autos) y Jorge (1 auto) creados.")

        # 4. Repuestos con stock inicial y movimientos (RN-01, RN-14, RN-20)
        rep_filtro = Repuesto(
            codigo="FIL-001",
            descripcion="Filtro de aceite",
            precio=Decimal("8500.00"),
            stock=10,
        )
        rep_pastillas = Repuesto(
            codigo="PAS-002",
            descripcion="Pastillas de freno",
            precio=Decimal("32000.00"),
            stock=4,
        )
        rep_bujia = Repuesto(
            codigo="BUJ-003",
            descripcion="Bujía",
            precio=Decimal("4500.00"),
            stock=2,
        )
        rep_aceite = Repuesto(
            codigo="ACE-004",
            descripcion="Aceite por litro",
            precio=Decimal("12000.00"),
            stock=20,
        )
        session.add_all([rep_filtro, rep_pastillas, rep_bujia, rep_aceite])
        await session.flush()

        # Movimientos de stock iniciales
        movimientos = [
            MovimientoStock(
                repuesto_id=rep_filtro.id,  # type: ignore[arg-type]
                usuario_id=u_admin.id,
                cantidad=10,
                motivo="Stock inicial",
            ),
            MovimientoStock(
                repuesto_id=rep_pastillas.id,  # type: ignore[arg-type]
                usuario_id=u_admin.id,
                cantidad=4,
                motivo="Stock inicial",
            ),
            MovimientoStock(
                repuesto_id=rep_bujia.id,  # type: ignore[arg-type]
                usuario_id=u_admin.id,
                cantidad=2,
                motivo="Stock inicial",
            ),
            MovimientoStock(
                repuesto_id=rep_aceite.id,  # type: ignore[arg-type]
                usuario_id=u_admin.id,
                cantidad=20,
                motivo="Stock inicial",
            ),
        ]
        session.add_all(movimientos)

        # Historial de variación de precio para el filtro (de 8000 a 8500) (RN-20)
        hist_precio = HistorialPrecioRepuesto(
            repuesto_id=rep_filtro.id,  # type: ignore[arg-type]
            usuario_id=u_admin.id,
            precio_anterior=Decimal("8000.00"),
            precio_nuevo=Decimal("8500.00"),
        )
        session.add(hist_precio)

        # Evento de seguridad de inicialización con actor SISTEMA
        evento_seg = EventoSeguridad(
            actor="SISTEMA",
            accion="Carga de los datos iniciales",
        )
        session.add(evento_seg)
        await session.flush()
        logger.info("Repuestos, stock inicial, histórico de precio y auditoría cargados.")

        # 5. Órdenes de trabajo canónicas (RN-10, RN-11, RN-13)
        # Orden 1: PENDIENTE, sobre primer vehículo de Laura
        ord1 = OrdenTrabajo(
            vehiculo_id=v_laura1.id,  # type: ignore[arg-type]
            mecanico_id=None,
            estado="PENDIENTE",
            falla="Ruido al frenar en frío",
            total=Decimal("32000.00"),
        )
        session.add(ord1)
        await session.flush()

        item_ord1 = ItemOrden(
            orden_id=ord1.id,  # type: ignore[arg-type]
            repuesto_id=rep_pastillas.id,  # type: ignore[arg-type]
            cantidad=1,
            precio_unitario=Decimal("32000.00"),
        )
        hist_ord1 = HistorialEstadoOrden(
            orden_id=ord1.id,  # type: ignore[arg-type]
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=u_recep.id,
        )
        session.add_all([item_ord1, hist_ord1])

        # Orden 2: EN_REPARACION, sobre vehículo de Jorge, asignada a mecánico titular, pidiendo 4 bujías
        # (Al haber solo 2 en stock, permite validar el rechazo y rollback por falta de stock RN-13)
        ord2 = OrdenTrabajo(
            vehiculo_id=v_jorge.id,  # type: ignore[arg-type]
            mecanico_id=u_mec.id,
            estado="EN_REPARACION",
            falla="Falla en baja y consumo excesivo",
            total=Decimal("18000.00"),  # 4 * 4500.00
        )
        session.add(ord2)
        await session.flush()

        item_ord2 = ItemOrden(
            orden_id=ord2.id,  # type: ignore[arg-type]
            repuesto_id=rep_bujia.id,  # type: ignore[arg-type]
            cantidad=4,
            precio_unitario=Decimal("4500.00"),
        )
        hist_ord2_a = HistorialEstadoOrden(
            orden_id=ord2.id,  # type: ignore[arg-type]
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=u_recep.id,
        )
        hist_ord2_b = HistorialEstadoOrden(
            orden_id=ord2.id,  # type: ignore[arg-type]
            desde_estado="PENDIENTE",
            hasta_estado="EN_REPARACION",
            usuario_id=u_mec.id,
        )
        session.add_all([item_ord2, hist_ord2_a, hist_ord2_b])

        await session.commit()
        logger.info("Órdenes canónicas #1 (PENDIENTE) y #2 (EN_REPARACION) insertadas.")

    await engine.dispose()
    logger.info("Siembra completada con éxito.")


if __name__ == "__main__":
    asyncio.run(seed_database())
