from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Numeric, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.ordenes.models import ItemOrden, OrdenTrabajo
    from app.modules.usuarios.models import Usuario


class Repuesto(SQLModel, table=True):
    __tablename__ = "repuesto"
    __table_args__ = (
        CheckConstraint("precio > 0", name="ck_repuesto_precio_positivo"),
        CheckConstraint("stock >= 0", name="ck_repuesto_stock_no_negativo"),
        Index(
            "ix_repuesto_codigo_vigente",
            "codigo",
            unique=True,
            postgresql_where=text("borrado_en IS NULL"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(nullable=False)
    descripcion: str = Field(nullable=False)
    precio: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
    )
    stock: int = Field(default=0, nullable=False)
    borrado_en: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    items_orden: list["ItemOrden"] = Relationship(back_populates="repuesto")
    movimientos: list["MovimientoStock"] = Relationship(back_populates="repuesto")
    historial_precios: list["HistorialPrecioRepuesto"] = Relationship(
        back_populates="repuesto"
    )


class MovimientoStock(SQLModel, table=True):
    __tablename__ = "movimiento_stock"
    __table_args__ = (
        CheckConstraint("cantidad <> 0", name="ck_movimiento_stock_cantidad_no_cero"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", nullable=False, index=True)
    orden_id: Optional[int] = Field(
        default=None,
        foreign_key="orden_trabajo.id",
        nullable=True,
        index=True,
    )
    usuario_id: int = Field(foreign_key="usuario.id", nullable=False, index=True)
    cantidad: int = Field(nullable=False)
    motivo: str = Field(nullable=False)
    cuando: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    repuesto: Optional["Repuesto"] = Relationship(back_populates="movimientos")
    orden: Optional["OrdenTrabajo"] = Relationship(back_populates="movimientos_stock")
    usuario: Optional["Usuario"] = Relationship(back_populates="movimientos_stock")


class HistorialPrecioRepuesto(SQLModel, table=True):
    __tablename__ = "historial_precio_repuesto"
    __table_args__ = (
        CheckConstraint(
            "precio_nuevo > 0",
            name="ck_historial_precio_repuesto_nuevo_positivo",
        ),
        CheckConstraint(
            "precio_nuevo <> precio_anterior",
            name="ck_historial_precio_repuesto_distinto",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", nullable=False, index=True)
    usuario_id: int = Field(foreign_key="usuario.id", nullable=False, index=True)
    precio_anterior: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
    )
    precio_nuevo: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
    )
    cuando: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    repuesto: Optional["Repuesto"] = Relationship(back_populates="historial_precios")
    usuario: Optional["Usuario"] = Relationship(back_populates="cambios_precio_repuesto")
