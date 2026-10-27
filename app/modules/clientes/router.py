from fastapi import APIRouter, Depends, Response, status
from app.core.dependencies import get_current_active_user, get_uow, requiere_rol
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.schemas import (
    ClienteResponse,
    CrearClienteRequest,
    CrearVehiculoRequest,
    VehiculoResponse,
)
from app.modules.clientes.service import ClientesService
from app.modules.usuarios.models import Usuario

router = APIRouter(tags=["clientes", "vehiculos"])


@router.post(
    "/clientes",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_cliente(
    payload: CrearClienteRequest,
    _user: Usuario = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> ClienteResponse:
    service = ClientesService(uow)
    cliente = await service.crear_cliente(payload)
    return ClienteResponse.model_validate(cliente)


@router.get(
    "/clientes/{id}",
    response_model=ClienteResponse,
    status_code=status.HTTP_200_OK,
)
async def obtener_cliente(
    id: int,
    _user: Usuario = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> ClienteResponse:
    service = ClientesService(uow)
    cliente = await service.obtener_cliente(id)
    return ClienteResponse.model_validate(cliente)


@router.post(
    "/clientes/{id}/vehiculos",
    response_model=VehiculoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_vehiculo(
    id: int,
    payload: CrearVehiculoRequest,
    _user: Usuario = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> VehiculoResponse:
    service = ClientesService(uow)
    vehiculo = await service.registrar_vehiculo(id, payload)
    return VehiculoResponse.model_validate(vehiculo)


@router.delete(
    "/vehiculos/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def eliminar_vehiculo(
    id: int,
    _user: Usuario = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    service = ClientesService(uow)
    await service.eliminar_vehiculo(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/mis-vehiculos",
    response_model=list[VehiculoResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_mis_vehiculos(
    current_user: Usuario = Depends(get_current_active_user),
    uow: UnitOfWork = Depends(get_uow),
) -> list[VehiculoResponse]:
    assert current_user.id is not None
    service = ClientesService(uow)
    vehiculos = await service.listar_mis_vehiculos(current_user.id)
    return [VehiculoResponse.model_validate(v) for v in vehiculos]
