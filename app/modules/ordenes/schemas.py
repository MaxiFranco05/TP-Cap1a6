from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==============================================================================
# Contratos de Entrada (Requests) - Regla Dura 1: extra="forbid"
# ==============================================================================

class ItemOrdenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repuesto_id: int = Field(gt=0, description="Identificador del repuesto")
    cantidad: int = Field(gt=0, description="Cantidad requerida del repuesto (debe ser > 0)")


class CrearOrdenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehiculo_id: int = Field(gt=0, description="Identificador del vehículo a reparar")
    falla: str = Field(min_length=1, max_length=500, description="Descripción de la falla reportada")
    items: list[ItemOrdenInput] = Field(min_length=1, description="Lista de repuestos requeridos (al menos uno)")

    @field_validator("items")
    @classmethod
    def validar_repuestos_no_repetidos(cls, items: list[ItemOrdenInput]) -> list[ItemOrdenInput]:
        repuesto_ids = [item.repuesto_id for item in items]
        if len(repuesto_ids) != len(set(repuesto_ids)):
            raise ValueError("No se permiten repuestos repetidos en los ítems de una orden")
        return items


# ==============================================================================
# Contratos de Salida (Responses) - Regla Dura 1: extra="forbid"
# ==============================================================================

class EstadoOrdenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    codigo: str
    descripcion: str
    posicion: int
    es_final: bool


class ItemOrdenDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    repuesto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal


class HistorialEstadoOrdenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    desde_estado: Optional[str] = None
    hasta_estado: str
    usuario_id: int
    cuando: datetime


class OrdenTrabajoDetalleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    estado: str
    patente: str
    total: Decimal
    creada_en: datetime
    mecanico_id: Optional[int] = None
    falla: str
    cliente: str
    items: list[ItemOrdenDetalleResponse]
    historial: list[HistorialEstadoOrdenResponse]


class OrdenTrabajoResumenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    vehiculo_id: int
    mecanico_id: Optional[int] = None
    estado: str
    falla: str
    creada_en: datetime
    total: Decimal
