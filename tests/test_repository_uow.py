from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from app.core.config import get_settings
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden
from app.modules.repuestos.models import Repuesto
from app.modules.usuarios.models import Usuario


def test_repository_hierarchy_contracts() -> None:
    from app.core.repository import BaseRepository, ReadOnlyRepository, SoftDeleteRepository

    assert issubclass(SoftDeleteRepository, BaseRepository)
    assert not issubclass(ReadOnlyRepository, BaseRepository)

    # SoftDeleteRepository methods must NOT exist on BaseRepository
    assert not hasattr(BaseRepository, "get_by_id_including_deleted")
    assert not hasattr(BaseRepository, "soft_delete")
    assert hasattr(SoftDeleteRepository, "get_by_id_including_deleted")
    assert hasattr(SoftDeleteRepository, "soft_delete")

    # ReadOnlyRepository must NOT expose write methods
    for write_method in ("add", "update", "delete", "soft_delete"):
        assert not hasattr(ReadOnlyRepository, write_method)


@pytest.mark.asyncio
async def test_base_repository_flush_never_commits() -> None:
    from app.core.repository import BaseRepository

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.delete = AsyncMock()

    repo = BaseRepository(mock_session, Usuario)
    assert repo.session is mock_session
    assert repo.model_cls is Usuario

    user = Usuario(
        email="flush_test@example.com",
        nombre="Flush User",
        password_hash="hash123",
    )
    await repo.add(user)
    mock_session.add.assert_called_with(user)
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 0

    user.nombre = "Updated Name"
    await repo.update(user)
    assert mock_session.flush.await_count == 2
    assert mock_session.commit.await_count == 0

    await repo.delete(user)
    mock_session.delete.assert_awaited_once_with(user)
    assert mock_session.flush.await_count == 3
    assert mock_session.commit.await_count == 0


@pytest.mark.asyncio
async def test_repositories_integration_with_postgres() -> None:
    from app.core.repository import BaseRepository, ReadOnlyRepository, SoftDeleteRepository

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # Ejecutamos dentro de una transaccion que revertiremos al final para aislar el test
            cliente_repo = BaseRepository(session, Cliente)
            vehiculo_repo = SoftDeleteRepository(session, Vehiculo)
            estado_repo = ReadOnlyRepository(session, EstadoOrden, pk_attr="codigo")

            # Insertar estado_orden via session para probar ReadOnlyRepository
            est = EstadoOrden(
                codigo="PENDIENTE_TEST",
                descripcion="Pendiente de prueba",
                posicion=99,
                es_final=False,
            )
            session.add(est)
            await session.flush()

            fetched_est = await estado_repo.get_by_pk("PENDIENTE_TEST")
            assert fetched_est is not None
            assert fetched_est.descripcion == "Pendiente de prueba"
            all_estados = await estado_repo.get_all()
            assert any(e.codigo == "PENDIENTE_TEST" for e in all_estados)
            assert await estado_repo.count() >= 1

            # Probar BaseRepository y SoftDeleteRepository + selectinload
            cliente = await cliente_repo.add(
                Cliente(
                    nombre="Laura Repo",
                    documento="DOC-REPO-01",
                    telefono="11223344",
                )
            )
            assert cliente.id is not None

            v1 = await vehiculo_repo.add(
                Vehiculo(
                    cliente_id=cliente.id,
                    patente="REPO111",
                    marca="Toyota",
                    modelo="Corolla",
                    anio=2021,
                )
            )
            v2 = await vehiculo_repo.add(
                Vehiculo(
                    cliente_id=cliente.id,
                    patente="REPO222",
                    marca="Honda",
                    modelo="Civic",
                    anio=2022,
                )
            )
            assert v1.id is not None and v2.id is not None

            # Eager loading con selectinload en get_by_id
            cliente_con_flota = await cliente_repo.get_by_id(
                cliente.id,
                options=[selectinload(Cliente.vehiculos)],
            )
            assert cliente_con_flota is not None
            assert len(cliente_con_flota.vehiculos) == 2

            # Soft delete de v1
            assert await vehiculo_repo.count() >= 2
            await vehiculo_repo.soft_delete(v1)
            assert v1.borrado_en is not None

            # get_by_id normal filtra borrado_en IS NULL -> retorna None
            assert await vehiculo_repo.get_by_id(v1.id) is None
            # get_by_id_including_deleted lo encuentra
            v1_deleted = await vehiculo_repo.get_by_id_including_deleted(v1.id)
            assert v1_deleted is not None
            assert v1_deleted.borrado_en is not None

            active_list = await vehiculo_repo.get_all()
            assert all(v.id != v1.id for v in active_list)
            assert any(v.id == v2.id for v in active_list)

            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unit_of_work_commits_and_never_closes_session() -> None:
    from app.core.unit_of_work import AbstractUnitOfWork, UnitOfWork

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    uow = UnitOfWork(mock_session)
    assert isinstance(uow, AbstractUnitOfWork)

    async with uow as active_uow:
        assert active_uow is uow

    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()
    mock_session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_on_exception_and_never_closes_session() -> None:
    from app.core.unit_of_work import UnitOfWork

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    uow = UnitOfWork(mock_session)
    with pytest.raises(RuntimeError, match="fallo simulado"):
        async with uow:
            raise RuntimeError("fallo simulado")

    mock_session.commit.assert_not_awaited()
    mock_session.rollback.assert_awaited_once()
    mock_session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_unit_of_work_atomic_rollback_with_postgres() -> None:
    from app.core.repository import BaseRepository
    from app.core.unit_of_work import UnitOfWork

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            uow = UnitOfWork(session)
            user_repo = BaseRepository(session, Usuario)
            cliente_repo = BaseRepository(session, Cliente)

            with pytest.raises(ValueError, match="abortar transaccion"):
                async with uow:
                    u = await user_repo.add(
                        Usuario(
                            email="atomic_uow@example.com",
                            nombre="Atomic User",
                            password_hash="hash",
                        )
                    )
                    await cliente_repo.add(
                        Cliente(
                            usuario_id=u.id,
                            nombre="Atomic Cliente",
                            documento="DOC-ATOMIC-999",
                            telefono="999",
                        )
                    )
                    raise ValueError("abortar transaccion")

            # Verificar que tras el rollback del UoW no quedo ninguna fila persistida
            from sqlalchemy import select
            res_u = await session.execute(select(Usuario).where(Usuario.email == "atomic_uow@example.com"))
            res_c = await session.execute(select(Cliente).where(Cliente.documento == "DOC-ATOMIC-999"))
            assert res_u.scalars().first() is None
            assert res_c.scalars().first() is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_global_database_exception_handlers_rn18() -> None:
    import httpx
    from sqlalchemy.exc import DataError, IntegrityError
    from main import app

    class FakeOrigUniqueError(Exception):
        sqlstate = "23505"
        pgcode = "23505"

        def __str__(self) -> str:
            return 'duplicate key value violates unique constraint "ix_usuario_email" DETAIL: Key (email)=(admin@example.com) already exists.'

    class FakeOrigCheckError(Exception):
        sqlstate = "23514"
        pgcode = "23514"

        def __str__(self) -> str:
            return 'new row for relation "repuesto" violates check constraint "ck_repuesto_precio_positivo"'

    class FakeOrigDataError(Exception):
        sqlstate = "22003"
        pgcode = "22003"

        def __str__(self) -> str:
            return "numeric field overflow"

    @app.get("/_test_rn18/unique")
    async def _route_unique() -> None:
        raise IntegrityError("INSERT INTO usuario ...", {}, FakeOrigUniqueError())

    @app.get("/_test_rn18/check")
    async def _route_check() -> None:
        raise IntegrityError("INSERT INTO repuesto ...", {}, FakeOrigCheckError())

    @app.get("/_test_rn18/data")
    async def _route_data() -> None:
        raise DataError("SELECT ...", {}, FakeOrigDataError())

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_u = await client.get("/_test_rn18/unique")
        assert res_u.status_code == 409
        body_u = res_u.text
        assert "ix_usuario_email" not in body_u
        assert "DETAIL:" not in body_u
        assert "Key (" not in body_u
        assert "INSERT INTO" not in body_u

        res_c = await client.get("/_test_rn18/check")
        assert res_c.status_code == 422
        body_c = res_c.text
        assert "ck_repuesto_precio_positivo" not in body_c
        assert "relation" not in body_c

        res_d = await client.get("/_test_rn18/data")
        assert res_d.status_code == 422
        body_d = res_d.text
        assert "numeric field overflow" not in body_d
        assert "SELECT" not in body_d
