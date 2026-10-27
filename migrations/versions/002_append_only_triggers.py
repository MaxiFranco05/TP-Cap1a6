"""append_only_triggers

Revision ID: 002
Revises: 001
Create Date: 2026-10-27 10:35:00.000000

# Migración escrita a mano y leída/revisada antes de aplicarla: instala la
# función PL/pgSQL y los 3 disparadores de sólo agregado (RN-15) sobre
# historial_estado_orden, movimiento_stock e historial_precio_repuesto.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Instala función y disparadores de sólo agregado (RN-15)."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION rechazar_mutacion_solo_agregado()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla % es de sólo agregado: no se permite %', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for tabla in (
        "historial_estado_orden",
        "movimiento_stock",
        "historial_precio_repuesto",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{tabla}_solo_agregado
            BEFORE UPDATE OR DELETE ON {tabla}
            FOR EACH ROW
            EXECUTE FUNCTION rechazar_mutacion_solo_agregado();
            """
        )


def downgrade() -> None:
    """Elimina los disparadores y la función de sólo agregado."""
    for tabla in (
        "historial_precio_repuesto",
        "movimiento_stock",
        "historial_estado_orden",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_solo_agregado ON {tabla};")

    op.execute("DROP FUNCTION IF EXISTS rechazar_mutacion_solo_agregado();")
