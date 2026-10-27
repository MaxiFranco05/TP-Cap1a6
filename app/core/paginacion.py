import math
from typing import Generic, TypeVar
from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def calcular_paginas(total: int, size: int) -> int:
    """Calcula la cantidad total de páginas redondeando hacia arriba. Mínimo 1 si total es 0."""
    if total <= 0:
        return 1
    return math.ceil(total / size)


class PaginacionWrapper(BaseModel, Generic[T]):
    """Envoltorio estándar para respuestas paginadas del sistema."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int = Field(ge=0, description="Cantidad total de registros encontrados")
    page: int = Field(ge=1, description="Número de página actual (base 1)")
    size: int = Field(ge=1, le=100, description="Tamaño de la página solicitada (1..100)")
    pages: int = Field(ge=1, description="Cantidad total de páginas calculadas")


def crear_paginacion(items: list[T], total: int, page: int, size: int) -> PaginacionWrapper[T]:
    """Helper para construir el envoltorio calculando automáticamente el número de páginas.
    Si se solicita una página más allá de la última, responde HTTP 422 según consigna oficial.
    """
    pages = calcular_paginas(total=total, size=size)
    if page > pages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La página {page} no existe: hay {pages}",
        )
    return PaginacionWrapper[T](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


class ParametrosPaginacion(BaseModel):
    """Parámetros de consulta para endpoints paginados."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="Número de página a consultar (>= 1)")
    size: int = Field(default=20, ge=1, le=100, description="Registros por página (1..100, por defecto 20)")
