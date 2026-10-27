from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Vehiculo
    from app.modules.repuestos.models import MovimientoStock, Repuesto
    from app.modules.usuarios.models import Usuario


class EstadoOrdenEnum(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_REPARACION = "EN_REPARACION"
    TERMINADA = "TERMINADA"
    CANCELADA = "CANCELADA"


class EstadoOrden(SQLModel, table=True):
    __tablename__ = "estado_orden"

    codigo: str = Field(primary_key=True)
    descripcion: str = Field(nullable=False)
    posicion: int = Field(unique=True, nullable=False)
    es_final: bool = Field(default=False, nullable=False)

    ordenes: list["OrdenTrabajo"] = Relationship(back_populates="estado_rel")


class OrdenTrabajo(SQLModel, table=True):
    __tablename__ = "orden_trabajo"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_orden_trabajo_total_no_negativo"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    vehiculo_id: int = Field(foreign_key="vehiculo.id", nullable=False, index=True)
    mecanico_id: Optional[int] = Field(
        default=None,
        foreign_key="usuario.id",
        nullable=True,
        index=True,
    )
    estado: str = Field(foreign_key="estado_orden.codigo", nullable=False, index=True)
    falla: str = Field(nullable=False)
    creada_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    total: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(12, 2), nullable=False),
    )

    vehiculo: Optional["Vehiculo"] = Relationship(back_populates="ordenes")
    mecanico: Optional["Usuario"] = Relationship(
        back_populates="ordenes_asignadas",
        sa_relationship_kwargs={"foreign_keys": "[OrdenTrabajo.mecanico_id]"},
    )
    estado_rel: Optional["EstadoOrden"] = Relationship(back_populates="ordenes")
    items: list["ItemOrden"] = Relationship(back_populates="orden")
    historial: list["HistorialEstadoOrden"] = Relationship(back_populates="orden")
    movimientos_stock: list["MovimientoStock"] = Relationship(back_populates="orden")


class ItemOrden(SQLModel, table=True):
    __tablename__ = "item_orden"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_item_orden_cantidad_positiva"),
        CheckConstraint(
            "precio_unitario > 0",
            name="ck_item_orden_precio_unitario_positivo",
        ),
        UniqueConstraint(
            "orden_id",
            "repuesto_id",
            name="uq_item_orden_orden_repuesto",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", nullable=False, index=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", nullable=False, index=True)
    cantidad: int = Field(nullable=False)
    precio_unitario: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
    )

    orden: Optional["OrdenTrabajo"] = Relationship(back_populates="items")
    repuesto: Optional["Repuesto"] = Relationship(back_populates="items_orden")


class HistorialEstadoOrden(SQLModel, table=True):
    __tablename__ = "historial_estado_orden"

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", nullable=False, index=True)
    desde_estado: Optional[str] = Field(
        default=None,
        foreign_key="estado_orden.codigo",
        nullable=True,
        index=True,
    )
    hasta_estado: str = Field(
        foreign_key="estado_orden.codigo",
        nullable=False,
        index=True,
    )
    usuario_id: int = Field(foreign_key="usuario.id", nullable=False, index=True)
    cuando: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    orden: Optional["OrdenTrabajo"] = Relationship(back_populates="historial")
    desde_estado_rel: Optional["EstadoOrden"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[HistorialEstadoOrden.desde_estado]"},
    )
    hasta_estado_rel: Optional["EstadoOrden"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[HistorialEstadoOrden.hasta_estado]"},
    )
    usuario: Optional["Usuario"] = Relationship(back_populates="cambios_estado_orden")
