import asyncio
from decimal import Decimal
import logging
from typing import Optional
from fastapi import BackgroundTasks, HTTPException, status
from app.core.paginacion import PaginacionWrapper, crear_paginacion
from app.modules.ordenes.models import HistorialEstadoOrden, ItemOrden, OrdenTrabajo
from app.modules.ordenes.schemas import (
    CrearOrdenRequest,
    EstadoOrdenResponse,
    HistorialEstadoOrdenResponse,
    ItemOrdenDetalleResponse,
    OrdenTrabajoDetalleResponse,
    OrdenTrabajoResumenResponse,
)
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import MovimientoStock

logger = logging.getLogger(__name__)


async def notificar_cliente_orden_terminada(
    orden_id: int,
    cliente_nombre: str = "",
    cliente_email: Optional[str] = None,
) -> None:
    """Simula el aviso al cliente en segundo plano sin llamadas bloqueantes (sección 3.9)."""
    await asyncio.sleep(0.5)
    destinatario = cliente_email or cliente_nombre or "Cliente"
    logger.info("Aviso enviado a cliente %s: Su orden #%d está terminada.", destinatario, orden_id)


class OrdenesService:
    """Lógica de negocio y transiciones de órdenes de trabajo (RN-10 a RN-13, RN-17, RN-19)."""

    def __init__(self, uow: OrdenesUnitOfWork) -> None:
        self.uow = uow

    @staticmethod
    def _to_detalle_response(orden: OrdenTrabajo) -> OrdenTrabajoDetalleResponse:
        """Mapea una entidad ORM OrdenTrabajo precargada a OrdenTrabajoDetalleResponse."""
        cliente_nombre = orden.vehiculo.cliente.nombre if orden.vehiculo and orden.vehiculo.cliente else "Desconocido"
        patente = orden.vehiculo.patente if orden.vehiculo else ""

        items_resp: list[ItemOrdenDetalleResponse] = []
        for it in orden.items:
            codigo = it.repuesto.codigo if it.repuesto else ""
            desc = it.repuesto.descripcion if it.repuesto else ""
            subtotal = it.precio_unitario * it.cantidad
            items_resp.append(
                ItemOrdenDetalleResponse(
                    repuesto_id=it.repuesto_id,
                    codigo=codigo,
                    descripcion=desc,
                    cantidad=it.cantidad,
                    precio_unitario=it.precio_unitario,
                    subtotal=subtotal,
                )
            )

        historial_resp: list[HistorialEstadoOrdenResponse] = []
        for h in orden.historial:
            historial_resp.append(
                HistorialEstadoOrdenResponse(
                    desde_estado=h.desde_estado,
                    hasta_estado=h.hasta_estado,
                    usuario_id=h.usuario_id,
                    cuando=h.cuando,
                )
            )

        return OrdenTrabajoDetalleResponse(
            id=orden.id,  # type: ignore[arg-type]
            estado=orden.estado,
            patente=patente,
            total=orden.total,
            creada_en=orden.creada_en,
            mecanico_id=orden.mecanico_id,
            falla=orden.falla,
            cliente=cliente_nombre,
            items=items_resp,
            historial=historial_resp,
        )

    async def listar_estados(self) -> list[EstadoOrdenResponse]:
        """Consulta el catálogo de estados ordenado por posición (RN-19)."""
        async with self.uow:
            estados = await self.uow.estados.list_ordered_by_posicion()
            return [EstadoOrdenResponse.model_validate(e) for e in estados]

    async def crear_orden(
        self,
        request: CrearOrdenRequest,
        usuario_id: int,
    ) -> OrdenTrabajoDetalleResponse:
        """Crea una orden con ítems, copia precios y calcula total en el servidor (RN-10, RN-19)."""
        async with self.uow:
            # RN-19: Si el catálogo está vacío, responder 409
            if await self.uow.estados.is_empty():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El catálogo de estados no está inicializado",
                )

            # Validar que el vehículo exista y esté activo
            vehiculo = await self.uow.vehiculos.get_by_id(request.vehiculo_id)
            if not vehiculo:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El vehículo con ID {request.vehiculo_id} no existe o fue dado de baja",
                )

            # Validar que todos los repuestos existan y calcular total
            total = Decimal("0.00")
            repuestos_map = {}
            for item_in in request.items:
                rep = await self.uow.repuestos.get_by_id(item_in.repuesto_id)
                if not rep:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"El repuesto con ID {item_in.repuesto_id} no existe o fue dado de baja",
                    )
                repuestos_map[item_in.repuesto_id] = rep
                total += rep.precio * item_in.cantidad

            # Crear la orden en estado PENDIENTE
            nueva_orden = OrdenTrabajo(
                vehiculo_id=vehiculo.id,  # type: ignore[arg-type]
                mecanico_id=None,
                estado="PENDIENTE",
                falla=request.falla,
                total=total,
            )
            await self.uow.ordenes.add(nueva_orden)
            assert nueva_orden.id is not None

            # Agregar ítems con precio copiado del repuesto
            for item_in in request.items:
                rep = repuestos_map[item_in.repuesto_id]
                item_entidad = ItemOrden(
                    orden_id=nueva_orden.id,
                    repuesto_id=rep.id,  # type: ignore[arg-type]
                    cantidad=item_in.cantidad,
                    precio_unitario=rep.precio,
                )
                await self.uow.items.add(item_entidad)

            # Registrar fila inicial de historial
            hist = HistorialEstadoOrden(
                orden_id=nueva_orden.id,
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=usuario_id,
            )
            await self.uow.historial.add(hist)

            detalle = await self.uow.ordenes.get_detalle(nueva_orden.id)
            assert detalle is not None
            return self._to_detalle_response(detalle)

    async def iniciar_orden(
        self,
        orden_id: int,
        mecanico_id: int,
        roles: list[str],
    ) -> OrdenTrabajoDetalleResponse:
        """Inicia una orden pendiente, asignando al mecánico en sesión (RN-11)."""
        async with self.uow:
            if "MECANICO" not in roles and "ADMIN" not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un mecánico puede iniciar una orden de trabajo",
                )

            orden = await self.uow.ordenes.get_by_id(orden_id)
            if not orden:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Orden #{orden_id} no encontrada",
                )

            if orden.estado != "PENDIENTE":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede iniciar una orden en estado {orden.estado} (solo PENDIENTE)",
                )

            orden.estado = "EN_REPARACION"
            orden.mecanico_id = mecanico_id
            await self.uow.ordenes.update(orden)

            hist = HistorialEstadoOrden(
                orden_id=orden.id,  # type: ignore[arg-type]
                desde_estado="PENDIENTE",
                hasta_estado="EN_REPARACION",
                usuario_id=mecanico_id,
            )
            await self.uow.historial.add(hist)

            detalle = await self.uow.ordenes.get_detalle(orden.id)  # type: ignore[arg-type]
            assert detalle is not None
            return self._to_detalle_response(detalle)

    async def terminar_orden(
        self,
        orden_id: int,
        usuario_id: int,
        roles: list[str],
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> OrdenTrabajoDetalleResponse:
        """Termina una orden en reparación descontando stock en una sola transacción (RN-13, RN-14)."""
        async with self.uow:
            orden = await self.uow.ordenes.get_detalle(orden_id)
            if not orden:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Orden #{orden_id} no encontrada",
                )

            is_admin = "ADMIN" in roles
            is_assigned_mecanico = "MECANICO" in roles and orden.mecanico_id == usuario_id
            if not (is_admin or is_assigned_mecanico):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo el mecánico asignado o un administrador pueden terminar esta orden",
                )

            if orden.estado != "EN_REPARACION":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Solo se pueden terminar órdenes en estado EN_REPARACION (estado actual: {orden.estado})",
                )

            # Verificar que todos los repuestos tengan stock suficiente
            for it in orden.items:
                rep = await self.uow.repuestos.get_by_id_including_deleted(it.repuesto_id)
                if not rep or rep.stock < it.cantidad:
                    codigo_rep = rep.codigo if rep else str(it.repuesto_id)
                    disponible = rep.stock if rep else 0
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Stock insuficiente para el repuesto {codigo_rep}: "
                            f"disponible {disponible}, requerido {it.cantidad}"
                        ),
                    )

            target_id = orden.id
            assert target_id is not None

            # Descontar stock y registrar movimientos
            for it in orden.items:
                rep = await self.uow.repuestos.get_by_id_including_deleted(it.repuesto_id)
                assert rep is not None
                rep.stock -= it.cantidad
                await self.uow.repuestos.update(rep)

                mov = MovimientoStock(
                    repuesto_id=rep.id,  # type: ignore[arg-type]
                    orden_id=target_id,
                    usuario_id=usuario_id,
                    cantidad=-it.cantidad,
                    motivo=f"Consumo en orden de trabajo #{target_id}",
                )
                await self.uow.movimientos_stock.add(mov)

            orden.estado = "TERMINADA"
            await self.uow.ordenes.update(orden)

            hist = HistorialEstadoOrden(
                orden_id=target_id,
                desde_estado="EN_REPARACION",
                hasta_estado="TERMINADA",
                usuario_id=usuario_id,
            )
            await self.uow.historial.add(hist)

            self.uow.session.expire(orden, ["historial"])
            detalle = await self.uow.ordenes.get_detalle(target_id)
            assert detalle is not None

            if background_tasks is not None:
                cliente_nombre = detalle.vehiculo.cliente.nombre if detalle.vehiculo and detalle.vehiculo.cliente else "Cliente"
                background_tasks.add_task(
                    notificar_cliente_orden_terminada,
                    detalle.id,  # type: ignore[arg-type]
                    cliente_nombre,
                )

            return self._to_detalle_response(detalle)

    async def cancelar_orden(
        self,
        orden_id: int,
        usuario_id: int,
        roles: list[str],
        cliente_id: Optional[int],
    ) -> OrdenTrabajoDetalleResponse:
        """Cancela una orden con precedencia estricta de comprobación (403 antes que 409) (RN-12)."""
        async with self.uow:
            orden = await self.uow.ordenes.get_detalle(orden_id)
            if not orden:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Orden #{orden_id} no encontrada",
                )

            # RN-12: Evaluar permisos antes que el estado
            is_staff = any(r in roles for r in ["RECEPCION", "ADMIN"])
            is_owner = (
                cliente_id is not None
                and orden.vehiculo is not None
                and orden.vehiculo.cliente_id == cliente_id
            )
            if not (is_staff or is_owner):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permiso para cancelar esta orden",
                )

            target_id = orden.id
            assert target_id is not None

            if orden.estado != "PENDIENTE":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede cancelar una orden en estado {orden.estado} (solo PENDIENTE)",
                )

            orden.estado = "CANCELADA"
            await self.uow.ordenes.update(orden)

            hist = HistorialEstadoOrden(
                orden_id=target_id,
                desde_estado="PENDIENTE",
                hasta_estado="CANCELADA",
                usuario_id=usuario_id,
            )
            await self.uow.historial.add(hist)

            self.uow.session.expire(orden, ["historial"])
            detalle = await self.uow.ordenes.get_detalle(target_id)
            assert detalle is not None
            return self._to_detalle_response(detalle)

    async def obtener_orden_detalle(
        self,
        orden_id: int,
        usuario_id: int,
        roles: list[str],
        cliente_id: Optional[int],
    ) -> OrdenTrabajoDetalleResponse:
        """Obtiene el detalle de una orden asegurando aislamiento de clientes (RN-17)."""
        async with self.uow:
            orden = await self.uow.ordenes.get_detalle(orden_id)
            if not orden:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Orden #{orden_id} no encontrada",
                )

            is_staff = any(r in roles for r in ["ADMIN", "RECEPCION", "MECANICO"])
            is_owner = (
                cliente_id is not None
                and orden.vehiculo is not None
                and orden.vehiculo.cliente_id == cliente_id
            )
            if not (is_staff or is_owner):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene acceso a órdenes de otros clientes",
                )

            return self._to_detalle_response(orden)

    async def listar_ordenes(
        self,
        *,
        estado: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> PaginacionWrapper[OrdenTrabajoResumenResponse]:
        """Lista órdenes de trabajo con paginación y filtro opcional por estado."""
        if page < 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="page debe ser >= 1")
        if size < 1 or size > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="size debe estar entre 1 y 100")

        offset = (page - 1) * size
        async with self.uow:
            items, total = await self.uow.ordenes.list_paginado(
                estado=estado,
                offset=offset,
                limit=size,
            )
            resumen_items = [
                OrdenTrabajoResumenResponse(
                    id=o.id,  # type: ignore[arg-type]
                    vehiculo_id=o.vehiculo_id,
                    mecanico_id=o.mecanico_id,
                    estado=o.estado,
                    falla=o.falla,
                    creada_en=o.creada_en,
                    total=o.total,
                )
                for o in items
            ]
            return crear_paginacion(items=resumen_items, total=total, page=page, size=size)

    async def listar_mis_ordenes(
        self,
        cliente_id: int,
        page: int = 1,
        size: int = 20,
    ) -> PaginacionWrapper[OrdenTrabajoResumenResponse]:
        """Lista órdenes exclusivamente de los vehículos pertenecientes al cliente en sesión (RN-17)."""
        if page < 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="page debe ser >= 1")
        if size < 1 or size > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="size debe estar entre 1 y 100")

        async with self.uow:
            vehiculos = await self.uow.vehiculos.list_by_cliente_id(cliente_id)
            vehiculo_ids = [v.id for v in vehiculos if v.id is not None]
            if not vehiculo_ids:
                return crear_paginacion(items=[], total=0, page=page, size=size)

            offset = (page - 1) * size
            items, total = await self.uow.ordenes.list_paginado(
                vehiculo_ids=vehiculo_ids,
                offset=offset,
                limit=size,
            )
            resumen_items = [
                OrdenTrabajoResumenResponse(
                    id=o.id,  # type: ignore[arg-type]
                    vehiculo_id=o.vehiculo_id,
                    mecanico_id=o.mecanico_id,
                    estado=o.estado,
                    falla=o.falla,
                    creada_en=o.creada_en,
                    total=o.total,
                )
                for o in items
            ]
            return crear_paginacion(items=resumen_items, total=total, page=page, size=size)
