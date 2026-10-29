from fastapi import APIRouter, Depends, Request, Response, status
from app.core.dependencies import get_current_user, get_uow
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.schemas import (
    CambiarPasswordRequest,
    LoginRequest,
    LoginResponse,
    RegistroClienteRequest,
    UsuarioResponse,
)
from app.modules.usuarios.service import UsuariosService

auth_router = APIRouter(prefix="/auth", tags=["auth"])
router = auth_router


@auth_router.post(
    "/registro",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_cliente(
    payload: RegistroClienteRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> UsuarioResponse:
    service = UsuariosService(uow)
    return await service.registrar_cliente(payload)


@auth_router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
) -> LoginResponse:
    service = UsuariosService(uow)
    return await service.login(payload, request, response)


@auth_router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
async def logout(
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
) -> dict[str, str]:
    service = UsuariosService(uow)
    return service.logout(response)


@auth_router.get(
    "/yo",
    response_model=UsuarioResponse,
    status_code=status.HTTP_200_OK,
)
async def obtener_perfil_actual(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
) -> UsuarioResponse:
    service = UsuariosService(uow)
    return await service.obtener_perfil_actual(current_user, request)


@auth_router.post(
    "/cambiar-password",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def cambiar_password(
    payload: CambiarPasswordRequest,
    request: Request,
    response: Response,
    current_user: Usuario = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
) -> LoginResponse:
    service = UsuariosService(uow)
    return await service.cambiar_password(current_user, payload, request, response)
