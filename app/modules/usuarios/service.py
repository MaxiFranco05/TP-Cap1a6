from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request, Response, status
import jwt
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import (
    ACCESS_TOKEN_COOKIE_NAME,
    clear_auth_cookie,
    create_access_token,
    decode_access_token,
    get_dummy_hash,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    RolEnum,
    Usuario,
)
from app.modules.usuarios.repository import IntentoAccesoRepository
from app.modules.usuarios.schemas import (
    CambiarPasswordRequest,
    LoginRequest,
    LoginResponse,
    RegistroClienteRequest,
    UsuarioResponse,
)

RATE_LIMIT_MAX_FAILURES = 5
RATE_LIMIT_WINDOW_SECONDS = 60


class UsuariosService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    @asynccontextmanager
    async def _open_independent_session(
        self,
        request: Request | None = None,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Abre una sesión independiente para persistir intento_acceso (Ejercicio 7, RN-08).

        Cada intento de login (exitoso o fallido) es la única escritura del sistema que
        se ejecuta en una sesión y transacción propia con commit() inmediato fuera del
        UnitOfWork principal. Si compartiera la transacción de la petición, al lanzar
        HTTPException(401) el rollback revertiría el registro del intento fallido y el
        límite de 5 intentos en 60 segundos jamás se activaría.
        Su costo asumido: deja filas confirmadas en intento_acceso incluso cuando la
        petición falla o es rechazada.
        """
        bind = self.uow.session.bind
        if isinstance(bind, AsyncConnection):
            async with AsyncSession(
                bind=bind,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as indep_session:
                yield indep_session
            return

        if request is not None:
            app_obj = getattr(request, "app", None)
            overrides = getattr(app_obj, "dependency_overrides", {}) or {}
            session_factory = getattr(getattr(app_obj, "state", None), "session_factory", None)
            if get_session not in overrides and session_factory is not None:
                async with session_factory() as indep_session:
                    yield indep_session
                return

        async with AsyncSession(
            bind=bind,
            expire_on_commit=False,
        ) as indep_session:
            yield indep_session

    async def _registrar_intento_acceso(
        self,
        email: str,
        ip: str,
        exito: bool,
        request: Request | None = None,
    ) -> None:
        async with self._open_independent_session(request) as indep_session:
            repo = IntentoAccesoRepository(indep_session)
            await repo.add(
                IntentoAcceso(
                    email=email,
                    ip=ip,
                    exito=exito,
                )
            )
            await indep_session.commit()

    async def registrar_cliente(self, data: RegistroClienteRequest) -> UsuarioResponse:
        # Regla Dura #6: hashear la contraseña fuera de la transacción de base de datos
        password_hash = await hash_password(data.password)

        async with self.uow:
            existente_email = await self.uow.usuarios.get_by_email(data.email)
            if existente_email is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El email ya está registrado.",
                )

            usuario = Usuario(
                email=data.email,
                nombre=data.nombre,
                password_hash=password_hash,
                activo=True,
                debe_cambiar_password=False,
            )
            await self.uow.usuarios.add(usuario)
            assert usuario.id is not None

            await self.uow.asignaciones_rol.add(
                AsignacionRol(
                    usuario_id=usuario.id,
                    rol=RolEnum.CLIENTE,
                )
            )

            # RN-02: si el documento ya pertenece a un cliente previo, rechazar con 409
            # y revertir atómicamente el Usuario y AsignacionRol recién insertados.
            existente_doc = await self.uow.clientes.get_by_documento(data.documento)
            if existente_doc is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El documento ya pertenece a un cliente registrado.",
                )

            await self.uow.clientes.add(
                Cliente(
                    usuario_id=usuario.id,
                    nombre=data.nombre,
                    documento=data.documento,
                    telefono=data.telefono,
                )
            )

            await self.uow.eventos_seguridad.add(
                EventoSeguridad(
                    actor=usuario.email,
                    accion="Auto-registro de cliente",
                )
            )

            return UsuarioResponse(
                id=usuario.id,
                email=usuario.email,
                nombre=usuario.nombre,
                activo=usuario.activo,
                debe_cambiar_password=usuario.debe_cambiar_password,
                roles=[str(RolEnum.CLIENTE)],
                roles_token=[],
            )

    async def login(
        self,
        data: LoginRequest,
        request: Request,
        response: Response,
    ) -> LoginResponse:
        ip = request.client.host if request.client and request.client.host else "127.0.0.1"

        async with self.uow:
            fallos_recientes = await self.uow.intentos_acceso.count_consecutive_failures_in_window(
                email=data.email,
                ip=ip,
                window_seconds=RATE_LIMIT_WINDOW_SECONDS,
            )
            if fallos_recientes >= RATE_LIMIT_MAX_FAILURES:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Demasiados intentos fallidos. Intente nuevamente en 60 segundos.",
                    headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
                )

            user = await self.uow.usuarios.get_by_email(data.email)

        # Ejecutar verificación bcrypt fuera de la transacción de base de datos (Regla Dura #6)
        if user is None:
            dummy_hash = await get_dummy_hash(request)
            await verify_password(data.password, dummy_hash)
            await self._registrar_intento_acceso(
                email=data.email,
                ip=ip,
                exito=False,
                request=request,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        es_valida = await verify_password(data.password, user.password_hash)
        if not es_valida or not user.activo:
            await self._registrar_intento_acceso(
                email=data.email,
                ip=ip,
                exito=False,
                request=request,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        await self._registrar_intento_acceso(
            email=data.email,
            ip=ip,
            exito=True,
            request=request,
        )

        async with self.uow:
            assert user.id is not None
            roles_vigentes = await self.uow.asignaciones_rol.get_active_roles_by_usuario_id(user.id)

        settings = get_settings()
        token = create_access_token(
            usuario_id=user.id,
            roles=roles_vigentes,
            settings=settings,
        )
        set_auth_cookie(response, token, settings=settings)

        return LoginResponse(
            mensaje="Sesión iniciada",
            debe_cambiar_password=user.debe_cambiar_password,
            expira_en_segundos=settings.JWT_EXPIRATION_SECONDS,
        )

    def logout(self, response: Response) -> dict[str, str]:
        clear_auth_cookie(response)
        return {"mensaje": "Sesión cerrada"}

    async def obtener_perfil_actual(
        self,
        current_user: Usuario,
        request: Request,
    ) -> UsuarioResponse:
        assert current_user.id is not None
        roles_token: list[str] = []
        token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
        if token:
            try:
                payload = decode_access_token(token)
                raw_roles = payload.get("roles", [])
                if isinstance(raw_roles, list):
                    roles_token = [str(r) for r in raw_roles]
            except jwt.PyJWTError:
                roles_token = []

        async with self.uow:
            roles_db = await self.uow.asignaciones_rol.get_active_roles_by_usuario_id(
                current_user.id
            )

        return UsuarioResponse(
            id=current_user.id,
            email=current_user.email,
            nombre=current_user.nombre,
            activo=current_user.activo,
            debe_cambiar_password=current_user.debe_cambiar_password,
            roles=roles_db,
            roles_token=roles_token,
        )

    async def cambiar_password(
        self,
        current_user: Usuario,
        data: CambiarPasswordRequest,
        request: Request,
        response: Response,
    ) -> LoginResponse:
        assert current_user.id is not None

        # Regla Dura #6: verificar y hashear fuera de la transacción de base de datos
        es_actual_valida = await verify_password(data.password_actual, current_user.password_hash)
        if not es_actual_valida:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La contraseña actual es incorrecta.",
            )

        nuevo_hash = await hash_password(data.password_nueva)

        # RN-07: garantizar precisión de microsegundos monotónica respecto al token previo
        old_iat_val: float | None = None
        token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
        if token:
            try:
                payload = decode_access_token(token)
                raw_iat = payload.get("iat")
                if raw_iat is not None:
                    old_iat_val = float(raw_iat)
            except (jwt.PyJWTError, ValueError, TypeError):
                old_iat_val = None

        now_dt = datetime.now(timezone.utc)
        if old_iat_val is not None:
            old_iat_dt = datetime.fromtimestamp(old_iat_val, tz=timezone.utc)
            if now_dt <= old_iat_dt:
                now_dt = old_iat_dt + timedelta(microseconds=1)
            new_iat_ts = float(now_dt.timestamp())
            while datetime.fromtimestamp(new_iat_ts, tz=timezone.utc) <= old_iat_dt:
                now_dt = now_dt + timedelta(microseconds=1)
                new_iat_ts = float(now_dt.timestamp())
        else:
            new_iat_ts = float(now_dt.timestamp())

        cambio_dt = datetime.fromtimestamp(new_iat_ts, tz=timezone.utc)

        async with self.uow:
            user = await self.uow.usuarios.get_by_id(current_user.id)
            if user is None or not user.activo:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no encontrado o inactivo.",
                )

            user.password_hash = nuevo_hash
            user.debe_cambiar_password = False
            user.password_cambiada_en = cambio_dt
            await self.uow.usuarios.update(user)

            await self.uow.eventos_seguridad.add(
                EventoSeguridad(
                    actor=user.email,
                    accion="Cambio de contraseña",
                    cuando=cambio_dt,
                )
            )
            roles_vigentes = await self.uow.asignaciones_rol.get_active_roles_by_usuario_id(
                 current_user.id,
                now=cambio_dt,
            )

        settings = get_settings()
        new_token = create_access_token(
            usuario_id=current_user.id,
            roles=roles_vigentes,
            settings=settings,
            iat_timestamp=new_iat_ts,
        )
        set_auth_cookie(response, new_token, settings=settings)

        return LoginResponse(
            mensaje="Contraseña actualizada",
            debe_cambiar_password=False,
            expira_en_segundos=settings.JWT_EXPIRATION_SECONDS,
        )
