from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.core.dependencies import (
    get_current_active_user,
    get_current_cliente,
    get_current_user_roles,
    requiere_rol,
)
from app.core.paginacion import (
    PaginacionWrapper,
    ParametrosPaginacion,
    crear_paginacion,
    get_parametros_paginacion,
)
from app.modules.clientes.models import Cliente
from app.modules.ordenes.schemas import (
    CrearOrdenRequest,
    EstadoOrdenResponse,
    OrdenTrabajoDetalleResponse,
    OrdenTrabajoResumenResponse,
)
from app.modules.ordenes.service import OrdenesService
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.usuarios.models import Usuario

router = APIRouter(tags=["ordenes"])


def get_ordenes_uow(session: AsyncSession = Depends(get_session)) -> OrdenesUnitOfWork:
    return OrdenesUnitOfWork(session)


@router.get(
    "/estados-orden",
    response_model=list[EstadoOrdenResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_estados_orden(
    _user: Usuario = Depends(get_current_active_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> list[EstadoOrdenResponse]:
    """Consulta el catálogo inmutable de estados de orden ordenados por posición (RN-19)."""
    service = OrdenesService(uow)
    return await service.listar_estados()


@router.post(
    "/ordenes",
    response_model=OrdenTrabajoDetalleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_orden(
    payload: CrearOrdenRequest,
    current_user: Usuario = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenTrabajoDetalleResponse:
    """Crea una orden de trabajo atómicamente con sus ítems en estado PENDIENTE (RN-10)."""
    assert current_user.id is not None
    service = OrdenesService(uow)
    return await service.crear_orden(payload, usuario_id=current_user.id)


@router.get(
    "/ordenes",
    response_model=PaginacionWrapper[OrdenTrabajoResumenResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_ordenes(
    estado: str | None = Query(None, description="Filtrar por código de estado"),
    params: ParametrosPaginacion = Depends(get_parametros_paginacion),
    _user: Usuario = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO")),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> PaginacionWrapper[OrdenTrabajoResumenResponse]:
    """Lista órdenes de trabajo con paginación y precarga para personal del taller."""
    service = OrdenesService(uow)
    return await service.listar_ordenes(estado=estado, page=params.page, size=params.size)


@router.get(
    "/ordenes/{id}",
    response_model=OrdenTrabajoDetalleResponse,
    status_code=status.HTTP_200_OK,
)
async def obtener_orden_detalle(
    id: int,
    current_user: Usuario = Depends(get_current_active_user),
    roles: list[str] = Depends(get_current_user_roles),
    current_cliente: Cliente | None = Depends(get_current_cliente),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenTrabajoDetalleResponse:
    """Obtiene el detalle completo de una orden garantizando aislamiento de clientes (RN-17)."""
    assert current_user.id is not None
    service = OrdenesService(uow)
    cliente_id = current_cliente.id if current_cliente else None
    return await service.obtener_orden_detalle(
        orden_id=id,
        usuario_id=current_user.id,
        roles=roles,
        cliente_id=cliente_id,
    )


@router.post(
    "/ordenes/{id}/iniciar",
    response_model=OrdenTrabajoDetalleResponse,
    status_code=status.HTTP_200_OK,
)
async def iniciar_orden(
    id: int,
    current_user: Usuario = Depends(requiere_rol("MECANICO")),
    roles: list[str] = Depends(get_current_user_roles),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenTrabajoDetalleResponse:
    """Inicia la reparación de una orden pendiente asignando al mecánico en sesión (RN-11)."""
    assert current_user.id is not None
    service = OrdenesService(uow)
    return await service.iniciar_orden(
        orden_id=id,
        mecanico_id=current_user.id,
        roles=roles,
    )


@router.post(
    "/ordenes/{id}/terminar",
    response_model=OrdenTrabajoDetalleResponse,
    status_code=status.HTTP_200_OK,
)
async def terminar_orden(
    id: int,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(requiere_rol("ADMIN", "MECANICO")),
    roles: list[str] = Depends(get_current_user_roles),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenTrabajoDetalleResponse:
    """Finaliza una orden en reparación con descuento atómico de stock y aviso simulado (RN-13)."""
    assert current_user.id is not None
    service = OrdenesService(uow)
    return await service.terminar_orden(
        orden_id=id,
        usuario_id=current_user.id,
        roles=roles,
        background_tasks=background_tasks,
    )


@router.post(
    "/ordenes/{id}/cancelar",
    response_model=OrdenTrabajoDetalleResponse,
    status_code=status.HTTP_200_OK,
)
async def cancelar_orden(
    id: int,
    current_user: Usuario = Depends(get_current_active_user),
    roles: list[str] = Depends(get_current_user_roles),
    current_cliente: Cliente | None = Depends(get_current_cliente),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenTrabajoDetalleResponse:
    """Cancela una orden pendiente con precedencia estricta de comprobación (RN-12)."""
    assert current_user.id is not None
    service = OrdenesService(uow)
    cliente_id = current_cliente.id if current_cliente else None
    return await service.cancelar_orden(
        orden_id=id,
        usuario_id=current_user.id,
        roles=roles,
        cliente_id=cliente_id,
    )


@router.get(
    "/mis-ordenes",
    response_model=PaginacionWrapper[OrdenTrabajoResumenResponse],
    status_code=status.HTTP_200_OK,
)
async def listar_mis_ordenes(
    params: ParametrosPaginacion = Depends(get_parametros_paginacion),
    current_cliente: Cliente | None = Depends(get_current_cliente),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> PaginacionWrapper[OrdenTrabajoResumenResponse]:
    """Lista las órdenes de los vehículos del cliente autenticado en sesión (RN-17)."""
    if current_cliente is None or current_cliente.id is None:
        return crear_paginacion(items=[], total=0, page=params.page, size=params.size)
    service = OrdenesService(uow)
    return await service.listar_mis_ordenes(
        cliente_id=current_cliente.id,
        page=params.page,
        size=params.size,
    )
