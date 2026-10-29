from datetime import datetime
from decimal import Decimal
from typing import Self
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CrearRepuestoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    codigo: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    precio: Decimal = Field(gt=Decimal("0"), max_digits=10, decimal_places=2)
    stock_inicial: int = Field(default=0, ge=0)


class ActualizarRepuestoRequest(BaseModel):
    """Esquema de actualización parcial de repuesto.

    Omite deliberadamente el campo stock para que cualquier intento de enviarlo
    en PATCH /repuestos/{id} sea rechazado con HTTP 422 (RN-14).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    descripcion: str | None = Field(default=None, min_length=1)
    precio: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=10,
        decimal_places=2,
    )

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(
                    f"El campo '{field_name}' no puede ser nulo si se envía en la actualización."
                )
        return self


class ReponerStockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cantidad: int = Field(gt=0)
    motivo: str = Field(min_length=1)


class RepuestoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    descripcion: str
    precio: Decimal
    stock: int


class MovimientoStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repuesto_id: int
    orden_id: int | None = None
    usuario_id: int
    cantidad: int
    motivo: str
    cuando: datetime


class HistorialPrecioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repuesto_id: int
    usuario_id: int
    precio_anterior: Decimal
    precio_nuevo: Decimal
    cuando: datetime
