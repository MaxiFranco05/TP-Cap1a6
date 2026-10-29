from fastapi import APIRouter, Depends, Request, Response, status
from app.core.dependencies import get_current_user, get_uow, requiere_rol
from app.core.paginacion import (
    PaginacionWrapper,
    ParametrosPaginacion,
    get_parametros_paginacion,
)
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios.models import RolEnum, Usuario
from app.modules.usuarios.schemas import (
    AsignacionRolResponse,
    AsignarRolRequest,
    CambiarPasswordRequest,
    CrearUsuarioRequest,
    EventoSeguridadResponse,
    LoginRequest,
    LoginResponse,
    RegistroClienteRequest,
    UsuarioResponse,
)
from app.modules.usuarios.service import UsuariosService

auth_router = APIRouter(prefix="/auth", tags=["auth"])
usuarios_router = APIRouter(tags=["usuarios"])
eventos_router = APIRouter(tags=["eventos"])
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


@usuarios_router.post(
    "/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_usuario(
    payload: CrearUsuarioRequest,
    admin_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> UsuarioResponse:
    service = UsuariosService(uow)
    return await service.crear_usuario(admin_user, payload)


@usuarios_router.get(
    "/usuarios/{usuario_id}/roles",
    response_model=list[AsignacionRolResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_roles_usuario(
    usuario_id: int,
    _admin_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> list[AsignacionRolResponse]:
    service = UsuariosService(uow)
    return await service.listar_roles_usuario(usuario_id)


@usuarios_router.post(
    "/usuarios/{usuario_id}/roles",
    response_model=AsignacionRolResponse,
    status_code=status.HTTP_201_CREATED,
)
async def asignar_rol(
    usuario_id: int,
    payload: AsignarRolRequest,
    admin_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> AsignacionRolResponse:
    service = UsuariosService(uow)
    return await service.asignar_rol(admin_user, usuario_id, payload)


@usuarios_router.delete(
    "/usuarios/{usuario_id}/roles/{rol}",
    response_model=AsignacionRolResponse,
    status_code=status.HTTP_200_OK,
)
async def revocar_rol(
    usuario_id: int,
    rol: RolEnum,
    admin_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> AsignacionRolResponse:
    service = UsuariosService(uow)
    return await service.revocar_rol(admin_user, usuario_id, rol)


@eventos_router.get(
    "/eventos",
    response_model=PaginacionWrapper[EventoSeguridadResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_eventos_seguridad(
    params: ParametrosPaginacion = Depends(get_parametros_paginacion),
    _admin_user: Usuario = Depends(requiere_rol("ADMIN")),
    uow: UnitOfWork = Depends(get_uow),
) -> PaginacionWrapper[EventoSeguridadResponse]:
    service = UsuariosService(uow)
    return await service.listar_eventos_seguridad(params)
