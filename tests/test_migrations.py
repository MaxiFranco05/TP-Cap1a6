from pathlib import Path
import subprocess
import sys
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_EXE = Path(sys.executable).parent / "alembic.exe"


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [str(ALEMBIC_EXE), *args] if ALEMBIC_EXE.exists() else [sys.executable, "-m", "alembic", *args]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_migration_files_exist_and_have_review_comments() -> None:
    versions_dir = PROJECT_ROOT / "migrations" / "versions"
    migration_files = sorted(versions_dir.glob("*.py"))
    assert len(migration_files) == 2, f"Se esperaban 2 migraciones, se encontraron: {migration_files}"

    for mf in migration_files:
        content = mf.read_text(encoding="utf-8")
        assert "Revisada" in content or "leída" in content or "revisada" in content


@pytest.mark.asyncio
async def test_alembic_upgrade_downgrade_cycle_and_schema() -> None:
    # 1. Upgrade head sobre la base
    res_up1 = _run_alembic("upgrade", "head")
    assert res_up1.returncode == 0, f"alembic upgrade head falló:\n{res_up1.stderr}"

    # 2. Downgrade base
    res_down = _run_alembic("downgrade", "base")
    assert res_down.returncode == 0, f"alembic downgrade base falló:\n{res_down.stderr}"

    # 3. Re-upgrade head
    res_up2 = _run_alembic("upgrade", "head")
    assert res_up2.returncode == 0, f"alembic re-upgrade head falló:\n{res_up2.stderr}"

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            # Verificar las 13 tablas en public
            result = await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            )
            tables = {row[0] for row in result.fetchall()}
            expected_tables = {
                "usuario",
                "asignacion_rol",
                "intento_acceso",
                "evento_seguridad",
                "cliente",
                "vehiculo",
                "repuesto",
                "estado_orden",
                "orden_trabajo",
                "item_orden",
                "historial_estado_orden",
                "movimiento_stock",
                "historial_precio_repuesto",
            }
            assert expected_tables.issubset(tables)

            # Verificar que estado_orden fue creada vacía por las migraciones
            res_count = await conn.execute(text("SELECT COUNT(*) FROM estado_orden"))
            assert res_count.scalar_one() == 0

            # Verificar presencia de los 3 índices únicos parciales en pg_indexes
            res_idx = await conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"
                )
            )
            idx_defs = {row[0]: row[1] for row in res_idx.fetchall()}
            assert "ix_asignacion_rol_usuario_rol_vigente" in idx_defs
            assert "WHERE (revocada_en IS NULL)" in idx_defs["ix_asignacion_rol_usuario_rol_vigente"]
            assert "ix_vehiculo_patente_vigente" in idx_defs
            assert "WHERE (borrado_en IS NULL)" in idx_defs["ix_vehiculo_patente_vigente"]
            assert "ix_repuesto_codigo_vigente" in idx_defs
            assert "WHERE (borrado_en IS NULL)" in idx_defs["ix_repuesto_codigo_vigente"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_append_only_triggers_reject_update_and_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        # Preparar datos mínimos en una transacción que luego limpiaremos
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO estado_orden (codigo, descripcion, posicion, es_final)
                    VALUES ('PENDIENTE', 'Pendiente', 1, false)
                    ON CONFLICT (codigo) DO NOTHING;
                    """
                )
            )
            res_u = await conn.execute(
                text(
                    """
                    INSERT INTO usuario (email, nombre, password_hash, activo, debe_cambiar_password)
                    VALUES ('test_trigger@example.com', 'Tester', 'hash', true, false)
                    RETURNING id;
                    """
                )
            )
            user_id = res_u.scalar_one()

            res_c = await conn.execute(
                text(
                    """
                    INSERT INTO cliente (nombre, documento, telefono)
                    VALUES ('Cliente Trigger', '99999999', '123456')
                    RETURNING id;
                    """
                )
            )
            cliente_id = res_c.scalar_one()

            res_v = await conn.execute(
                text(
                    """
                    INSERT INTO vehiculo (cliente_id, patente, marca, modelo, anio)
                    VALUES (:cid, 'AA000ZZ', 'Ford', 'Fiesta', 2020)
                    RETURNING id;
                    """
                ),
                {"cid": cliente_id},
            )
            vehiculo_id = res_v.scalar_one()

            res_r = await conn.execute(
                text(
                    """
                    INSERT INTO repuesto (codigo, descripcion, precio, stock)
                    VALUES ('REP-TRG-1', 'Repuesto Test', 1000.00, 5)
                    RETURNING id;
                    """
                )
            )
            repuesto_id = res_r.scalar_one()

            res_o = await conn.execute(
                text(
                    """
                    INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total)
                    VALUES (:vid, 'PENDIENTE', 'Falla test', NOW(), 1000.00)
                    RETURNING id;
                    """
                ),
                {"vid": vehiculo_id},
            )
            orden_id = res_o.scalar_one()

            # Insertar 1 fila en cada una de las 3 tablas de sólo agregado
            res_heo = await conn.execute(
                text(
                    """
                    INSERT INTO historial_estado_orden (orden_id, desde_estado, hasta_estado, usuario_id, cuando)
                    VALUES (:oid, NULL, 'PENDIENTE', :uid, NOW())
                    RETURNING id;
                    """
                ),
                {"oid": orden_id, "uid": user_id},
            )
            heo_id = res_heo.scalar_one()

            res_ms = await conn.execute(
                text(
                    """
                    INSERT INTO movimiento_stock (repuesto_id, orden_id, usuario_id, cantidad, motivo, cuando)
                    VALUES (:rid, NULL, :uid, 5, 'Stock inicial', NOW())
                    RETURNING id;
                    """
                ),
                {"rid": repuesto_id, "uid": user_id},
            )
            ms_id = res_ms.scalar_one()

            res_hpr = await conn.execute(
                text(
                    """
                    INSERT INTO historial_precio_repuesto (repuesto_id, usuario_id, precio_anterior, precio_nuevo, cuando)
                    VALUES (:rid, :uid, 900.00, 1000.00, NOW())
                    RETURNING id;
                    """
                ),
                {"rid": repuesto_id, "uid": user_id},
            )
            hpr_id = res_hpr.scalar_one()

        # Verificar los 6 rechazos (UPDATE y DELETE sobre las 3 tablas)
        statements = [
            ("UPDATE historial_estado_orden SET cuando = NOW() WHERE id = :id", heo_id),
            ("DELETE FROM historial_estado_orden WHERE id = :id", heo_id),
            ("UPDATE movimiento_stock SET motivo = 'Alterado' WHERE id = :id", ms_id),
            ("DELETE FROM movimiento_stock WHERE id = :id", ms_id),
            ("UPDATE historial_precio_repuesto SET precio_nuevo = 1200.00 WHERE id = :id", hpr_id),
            ("DELETE FROM historial_precio_repuesto WHERE id = :id", hpr_id),
        ]

        for sql_stmt, row_id in statements:
            async with engine.connect() as conn:
                with pytest.raises(DBAPIError):
                    await conn.execute(text(sql_stmt), {"id": row_id})
                await conn.rollback()

    finally:
        await engine.dispose()
        # Dejar el esquema limpio re-ejecutando downgrade base -> upgrade head
        _run_alembic("downgrade", "base")
        _run_alembic("upgrade", "head")
