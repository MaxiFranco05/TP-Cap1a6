from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Cliente
    from app.modules.ordenes.models import HistorialEstadoOrden, OrdenTrabajo
    from app.modules.repuestos.models import HistorialPrecioRepuesto, MovimientoStock


class RolEnum(StrEnum):
    ADMIN = "ADMIN"
    RECEPCION = "RECEPCION"
    MECANICO = "MECANICO"
    CLIENTE = "CLIENTE"


class Usuario(SQLModel, table=True):
    __tablename__ = "usuario"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, nullable=False, index=True)
    nombre: str = Field(nullable=False)
    password_hash: str = Field(nullable=False)
    activo: bool = Field(default=True, nullable=False)
    debe_cambiar_password: bool = Field(default=False, nullable=False)
    password_cambiada_en: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    # Relacion 1 a 0..1: Usuario.cliente devuelve un objeto unico, no una lista
    cliente: Optional["Cliente"] = Relationship(
        back_populates="usuario",
        sa_relationship_kwargs={"uselist": False},
    )
    roles: list["AsignacionRol"] = Relationship(
        back_populates="usuario",
        sa_relationship_kwargs={"foreign_keys": "[AsignacionRol.usuario_id]"},
    )
    ordenes_asignadas: list["OrdenTrabajo"] = Relationship(
        back_populates="mecanico",
        sa_relationship_kwargs={"foreign_keys": "[OrdenTrabajo.mecanico_id]"},
    )
    movimientos_stock: list["MovimientoStock"] = Relationship(
        back_populates="usuario",
    )
    cambios_precio_repuesto: list["HistorialPrecioRepuesto"] = Relationship(
        back_populates="usuario",
    )
    cambios_estado_orden: list["HistorialEstadoOrden"] = Relationship(
        back_populates="usuario",
    )


class AsignacionRol(SQLModel, table=True):
    __tablename__ = "asignacion_rol"
    __table_args__ = (
        CheckConstraint(
            "rol IN ('ADMIN', 'RECEPCION', 'MECANICO', 'CLIENTE')",
            name="ck_asignacion_rol_rol_valido",
        ),
        Index(
            "ix_asignacion_rol_usuario_rol_vigente",
            "usuario_id",
            "rol",
            unique=True,
            postgresql_where=text("revocada_en IS NULL"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", nullable=False, index=True)
    rol: str = Field(nullable=False)
    desde: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    vence_en: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    revocada_en: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    otorgada_por: Optional[int] = Field(
        default=None,
        foreign_key="usuario.id",
        nullable=True,
        index=True,
    )

    usuario: Optional["Usuario"] = Relationship(
        back_populates="roles",
        sa_relationship_kwargs={"foreign_keys": "[AsignacionRol.usuario_id]"},
    )
    otorgante: Optional["Usuario"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AsignacionRol.otorgada_por]"},
    )


class IntentoAcceso(SQLModel, table=True):
    __tablename__ = "intento_acceso"
    __table_args__ = (
        Index("ix_intento_acceso_email_ip_cuando", "email", "ip", "cuando"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    email: str = Field(nullable=False)
    ip: str = Field(nullable=False)
    exito: bool = Field(nullable=False)


class EventoSeguridad(SQLModel, table=True):
    __tablename__ = "evento_seguridad"

    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    actor: str = Field(nullable=False)
    accion: str = Field(nullable=False)
