import pytest
from pydantic import ValidationError
from app.core.paginacion import (
    PaginacionWrapper,
    ParametrosPaginacion,
    calcular_paginas,
    crear_paginacion,
)


def test_calcular_paginas():
    assert calcular_paginas(total=0, size=10) == 1
    assert calcular_paginas(total=1, size=10) == 1
    assert calcular_paginas(total=10, size=10) == 1
    assert calcular_paginas(total=11, size=10) == 2
    assert calcular_paginas(total=25, size=10) == 3
    assert calcular_paginas(total=100, size=20) == 5


def test_paginacion_wrapper_format():
    wrapper = PaginacionWrapper[str](
        items=["item1", "item2"],
        total=2,
        page=1,
        size=10,
        pages=1,
    )
    assert wrapper.items == ["item1", "item2"]
    assert wrapper.total == 2
    assert wrapper.page == 1
    assert wrapper.size == 10
    assert wrapper.pages == 1
    assert wrapper.model_dump() == {
        "items": ["item1", "item2"],
        "total": 2,
        "page": 1,
        "size": 10,
        "pages": 1,
    }


def test_crear_paginacion_helper():
    items = ["a", "b", "c"]
    wrapper = crear_paginacion(items=items, total=25, page=2, size=10)
    assert wrapper.items == items
    assert wrapper.total == 25
    assert wrapper.page == 2
    assert wrapper.size == 10
    assert wrapper.pages == 3


def test_paginacion_wrapper_extra_field_rejected():
    with pytest.raises(ValidationError):
        PaginacionWrapper[str](
            items=["a"],
            total=1,
            page=1,
            size=10,
            pages=1,
            invalido="campo_extra",  # type: ignore[call-arg]
        )


def test_paginacion_size_out_of_range():
    with pytest.raises(ValidationError):
        PaginacionWrapper[str](items=[], total=0, page=1, size=0, pages=1)

    with pytest.raises(ValidationError):
        PaginacionWrapper[str](items=[], total=0, page=1, size=101, pages=1)


def test_paginacion_page_out_of_range():
    with pytest.raises(ValidationError):
        PaginacionWrapper[str](items=[], total=0, page=0, size=10, pages=1)


def test_parametros_paginacion():
    params = ParametrosPaginacion()
    assert params.page == 1
    assert params.size == 20

    custom = ParametrosPaginacion(page=2, size=50)
    assert custom.page == 2
    assert custom.size == 50

    with pytest.raises(ValidationError):
        ParametrosPaginacion(size=0)

    with pytest.raises(ValidationError):
        ParametrosPaginacion(size=101)

    with pytest.raises(ValidationError):
        ParametrosPaginacion(page=0)


def test_crear_paginacion_page_beyond_last_raises_422():
    from fastapi import HTTPException
    # total 4 with size 2 -> pages = 2. Requesting page 3 must raise 422: "La página 3 no existe: hay 2"
    with pytest.raises(HTTPException) as exc_info:
        crear_paginacion(items=[], total=4, page=3, size=2)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "La página 3 no existe: hay 2"

    # With total 0 -> pages = 1. Requesting page 1 is ok. Requesting page 2 must raise 422
    valid_empty = crear_paginacion(items=[], total=0, page=1, size=20)
    assert valid_empty.pages == 1
    assert valid_empty.total == 0
    assert valid_empty.items == []

    with pytest.raises(HTTPException) as exc_info_zero:
        crear_paginacion(items=[], total=0, page=2, size=20)
    assert exc_info_zero.value.status_code == 422
    assert exc_info_zero.value.detail == "La página 2 no existe: hay 1"
