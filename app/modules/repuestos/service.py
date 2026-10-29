from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from app.core.paginacion import PaginacionWrapper, ParametrosPaginacion, crear_paginacion
from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.schemas import (
    ActualizarRepuestoRequest,
    CrearRepuestoRequest,
    ReponerStockRequest,
    RepuestoResponse,
)


def _translate_integrity_error(exc: IntegrityError) -> HTTPException:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "23514":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los datos enviados no cumplen las restricciones de validez del dominio.",
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Ya existe un repuesto activo con ese código.",
    )


class RepuestosService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def registrar_movimiento_stock(
        self,
        repuesto: Repuesto,
        cantidad: int,
        motivo: str,
        usuario_id: int,
        orden_id: int | None = None,
    ) -> MovimientoStock:
        """Punto único de mutación de existencias de repuestos (RN-14).

        Debe invocarse dentro de un contexto transaccional activo del UnitOfWork.
        """
        if cantidad == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La cantidad del movimiento de stock no puede ser cero.",
            )

        if repuesto.stock + cantidad < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stock insuficiente para realizar la operación.",
            )

        if repuesto.id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repuesto no encontrado.",
            )

        repuesto.stock += cantidad
        await self.uow.repuestos.update(repuesto)

        movimiento = MovimientoStock(
            repuesto_id=repuesto.id,
            orden_id=orden_id,
            usuario_id=usuario_id,
            cantidad=cantidad,
            motivo=motivo,
        )
        return await self.uow.movimientos_stock.add(movimiento)

    async def crear_repuesto(
        self,
        data: CrearRepuestoRequest,
        usuario_id: int,
    ) -> Repuesto:
        try:
            async with self.uow:
                existente = await self.uow.repuestos.get_by_codigo(data.codigo)
                if existente is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Ya existe un repuesto activo con ese código.",
                    )

                repuesto = Repuesto(
                    codigo=data.codigo,
                    descripcion=data.descripcion,
                    precio=Decimal(data.precio).quantize(Decimal("0.01")),
                    stock=0,
                )
                await self.uow.repuestos.add(repuesto)

                if data.stock_inicial > 0:
                    await self.registrar_movimiento_stock(
                        repuesto=repuesto,
                        cantidad=data.stock_inicial,
                        motivo="Stock inicial",
                        usuario_id=usuario_id,
                    )

                return repuesto
        except IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc

    async def actualizar_repuesto(
        self,
        repuesto_id: int,
        data: ActualizarRepuestoRequest,
        usuario_id: int,
    ) -> Repuesto:
        cambios = data.model_dump(exclude_unset=True)
        for campo, valor in cambios.items():
            if valor is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"El campo '{campo}' no puede ser nulo.",
                )

        try:
            async with self.uow:
                repuesto = await self.uow.repuestos.get_by_id(repuesto_id)
                if repuesto is None or repuesto.id is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Repuesto no encontrado.",
                    )

                if "descripcion" in cambios:
                    repuesto.descripcion = str(cambios["descripcion"])

                if "precio" in cambios:
                    nuevo_precio = Decimal(cambios["precio"]).quantize(
                        Decimal("0.01")
                    )
                    precio_anterior = Decimal(repuesto.precio).quantize(
                        Decimal("0.01")
                    )
                    if nuevo_precio != precio_anterior:
                        repuesto.precio = nuevo_precio
                        await self.uow.historial_precios.add(
                            HistorialPrecioRepuesto(
                                repuesto_id=repuesto.id,
                                usuario_id=usuario_id,
                                precio_anterior=precio_anterior,
                                precio_nuevo=nuevo_precio,
                            )
                        )

                await self.uow.repuestos.update(repuesto)
                return repuesto
        except IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc

    async def reponer_stock(
        self,
        repuesto_id: int,
        data: ReponerStockRequest,
        usuario_id: int,
    ) -> Repuesto:
        try:
            async with self.uow:
                repuesto = await self.uow.repuestos.get_by_id(repuesto_id)
                if repuesto is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Repuesto no encontrado.",
                    )

                await self.registrar_movimiento_stock(
                    repuesto=repuesto,
                    cantidad=data.cantidad,
                    motivo=data.motivo,
                    usuario_id=usuario_id,
                )
                return repuesto
        except IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc

    async def eliminar_repuesto(self, repuesto_id: int) -> None:
        async with self.uow:
            repuesto = await self.uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado.",
                )
            await self.uow.repuestos.soft_delete(repuesto)

    async def listar_repuestos(
        self,
        params: ParametrosPaginacion,
        q: str | None = None,
    ) -> PaginacionWrapper[RepuestoResponse]:
        async with self.uow:
            total = await self.uow.repuestos.count_active(q=q)
            items = await self.uow.repuestos.search_active(
                q=q,
                offset=params.offset,
                limit=params.size,
            )
            dtos = [RepuestoResponse.model_validate(item) for item in items]
            return crear_paginacion(
                items=dtos,
                total=total,
                page=params.page,
                size=params.size,
            )

    async def obtener_repuesto(self, repuesto_id: int) -> Repuesto:
        async with self.uow:
            repuesto = await self.uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado.",
                )
            return repuesto

    async def listar_movimientos(
        self,
        repuesto_id: int,
    ) -> list[MovimientoStock]:
        async with self.uow:
            repuesto = await self.uow.repuestos.get_by_id_including_deleted(
                repuesto_id
            )
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado.",
                )
            return await self.uow.movimientos_stock.list_by_repuesto_id(repuesto_id)

    async def listar_precios(
        self,
        repuesto_id: int,
    ) -> list[HistorialPrecioRepuesto]:
        async with self.uow:
            repuesto = await self.uow.repuestos.get_by_id_including_deleted(
                repuesto_id
            )
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado.",
                )
            return await self.uow.historial_precios.list_by_repuesto_id(repuesto_id)
