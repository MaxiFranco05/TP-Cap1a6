from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from app.core.dependencies import get_uow, requiere_rol
from app.core.paginacion import (
    PaginacionWrapper,
    ParametrosPaginacion,
    get_parametros_paginacion,
)
from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.schemas import (
    ActualizarRepuestoRequest,
    CrearRepuestoRequest,
    HistorialPrecioResponse,
    MovimientoStockResponse,
    ReponerStockRequest,
    RepuestoResponse,
)
from app.modules.repuestos.service import RepuestosService
from app.modules.usuarios.models import Usuario

router = APIRouter(tags=["repuestos"])


@router.get(
    "/repuestos",
    response_model=PaginacionWrapper[RepuestoResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_repuestos(
    q: str | None = Query(default=None),
    params: ParametrosPaginacion = Depends(get_parametros_paginacion),
    _user: Usuario = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO")),
    uow: UnitOfWork = Depends(get_uow),
) -> PaginacionWrapper[RepuestoResponse]:
    service = RepuestosService(uow)
    return await service.listar_repuestos(params=params, q=q)


@router.get(
    "/repuestos/{id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
)
async def obtener_repuesto(
    id: int,
    _user: Usuario = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO")),
    uow: UnitOfWork = Depends(get_uow),
) -> RepuestoResponse:
    service = RepuestosService(uow)
    repuesto = await service.obtener_repuesto(id)
    return RepuestoResponse.model_validate(repuesto)


@router.post(
    "/repuestos",
    response_model=RepuestoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_repuesto(
    payload: CrearRepuestoRequest,
    current_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> RepuestoResponse:
    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado.",
        )
    service = RepuestosService(uow)
    repuesto = await service.crear_repuesto(payload, usuario_id=current_user.id)
    return RepuestoResponse.model_validate(repuesto)


@router.patch(
    "/repuestos/{id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
)
async def actualizar_repuesto(
    id: int,
    payload: ActualizarRepuestoRequest,
    current_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> RepuestoResponse:
    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado.",
        )
    service = RepuestosService(uow)
    repuesto = await service.actualizar_repuesto(
        id, payload, usuario_id=current_user.id
    )
    return RepuestoResponse.model_validate(repuesto)


@router.delete(
    "/repuestos/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def eliminar_repuesto(
    id: int,
    _user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    service = RepuestosService(uow)
    await service.eliminar_repuesto(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/repuestos/{id}/reponer",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
)
async def reponer_stock(
    id: int,
    payload: ReponerStockRequest,
    current_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> RepuestoResponse:
    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado.",
        )
    service = RepuestosService(uow)
    repuesto = await service.reponer_stock(id, payload, usuario_id=current_user.id)
    return RepuestoResponse.model_validate(repuesto)


@router.get(
    "/repuestos/{id}/movimientos",
    response_model=list[MovimientoStockResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_movimientos(
    id: int,
    _user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> list[MovimientoStockResponse]:
    service = RepuestosService(uow)
    movimientos = await service.listar_movimientos(id)
    return [MovimientoStockResponse.model_validate(m) for m in movimientos]


@router.get(
    "/repuestos/{id}/precios",
    response_model=list[HistorialPrecioResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_precios(
    id: int,
    _user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> list[HistorialPrecioResponse]:
    service = RepuestosService(uow)
    precios = await service.listar_precios(id)
    return [HistorialPrecioResponse.model_validate(p) for p in precios]
