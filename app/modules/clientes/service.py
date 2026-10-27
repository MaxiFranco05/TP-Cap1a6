from fastapi import HTTPException, status
from sqlalchemy.orm.attributes import set_committed_value
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.schemas import CrearClienteRequest, CrearVehiculoRequest


class ClientesService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def crear_cliente(self, data: CrearClienteRequest) -> Cliente:
        async with self.uow:
            existente = await self.uow.clientes.get_by_documento(data.documento)
            if existente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe un cliente registrado con ese documento.",
                )

            cliente = Cliente(
                usuario_id=None,
                nombre=data.nombre,
                documento=data.documento,
                telefono=data.telefono,
            )
            await self.uow.clientes.add(cliente)
            set_committed_value(cliente, "vehiculos", [])
            return cliente

    async def obtener_cliente(self, cliente_id: int) -> Cliente:
        async with self.uow:
            cliente = await self.uow.clientes.get_by_id_with_vehiculos(cliente_id)
            if cliente is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado.",
                )
            return cliente

    async def registrar_vehiculo(
        self,
        cliente_id: int,
        data: CrearVehiculoRequest,
    ) -> Vehiculo:
        async with self.uow:
            cliente = await self.uow.clientes.get_by_id(cliente_id)
            if cliente is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado.",
                )

            patente_activa = await self.uow.vehiculos.get_by_patente_activa(data.patente)
            if patente_activa is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe un vehículo activo registrado con esa patente.",
                )

            vehiculo = Vehiculo(
                cliente_id=cliente_id,
                patente=data.patente,
                marca=data.marca,
                modelo=data.modelo,
                anio=data.anio,
            )
            await self.uow.vehiculos.add(vehiculo)
            return vehiculo

    async def eliminar_vehiculo(self, vehiculo_id: int) -> None:
        async with self.uow:
            vehiculo = await self.uow.vehiculos.get_by_id(vehiculo_id)
            if vehiculo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vehículo no encontrado.",
                )

            if await self.uow.vehiculos.has_open_orders(vehiculo_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se puede dar de baja un vehículo con órdenes de trabajo abiertas.",
                )

            await self.uow.vehiculos.soft_delete(vehiculo)

    async def listar_mis_vehiculos(self, usuario_id: int) -> list[Vehiculo]:
        async with self.uow:
            cliente = await self.uow.clientes.get_by_usuario_id(usuario_id)
            if cliente is None or cliente.id is None:
                return []
            return await self.uow.vehiculos.list_by_cliente_id(cliente.id)

