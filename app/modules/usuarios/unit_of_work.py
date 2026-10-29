from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
from app.modules.usuarios.repository import (
    AsignacionRolRepository,
    EventoSeguridadRepository,
    IntentoAccesoRepository,
    UsuarioRepository,
)


class UsuariosUnitOfWork(UnitOfWork):
    """Unit of Work específico para el módulo de usuarios y autenticación."""

    usuarios: UsuarioRepository
    asignaciones_rol: AsignacionRolRepository
    intentos_acceso: IntentoAccesoRepository
    eventos_seguridad: EventoSeguridadRepository
    clientes: ClienteRepository
    vehiculos: VehiculoRepository

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.usuarios = UsuarioRepository(session)
        self.asignaciones_rol = AsignacionRolRepository(session)
        self.intentos_acceso = IntentoAccesoRepository(session)
        self.eventos_seguridad = EventoSeguridadRepository(session)
        self.clientes = ClienteRepository(session)
        self.vehiculos = VehiculoRepository(session)

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.usuarios = UsuarioRepository(self.session)
        self.asignaciones_rol = AsignacionRolRepository(self.session)
        self.intentos_acceso = IntentoAccesoRepository(self.session)
        self.eventos_seguridad = EventoSeguridadRepository(self.session)
        self.clientes = ClienteRepository(self.session)
        self.vehiculos = VehiculoRepository(self.session)
        return self
