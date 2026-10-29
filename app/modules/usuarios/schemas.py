from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.security import validate_password_utf8_bytes
from app.modules.usuarios.models import RolEnum


def _check_password_bytes(value: str) -> str:
    validate_password_utf8_bytes(value)
    return value


class RegistroClienteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    documento: str = Field(min_length=1)
    telefono: str = Field(min_length=1)

    @field_validator("email", "nombre", "documento", "telefono")
    @classmethod
    def _strip_and_require_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("El campo no puede estar vacío.")
        return stripped

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, v: str) -> str:
        return _check_password_bytes(v)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _strip_email(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("El email no puede estar vacío.")
        return stripped

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, v: str) -> str:
        return _check_password_bytes(v)


class CambiarPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password_actual: str = Field(min_length=1)
    password_nueva: str = Field(min_length=1)

    @field_validator("password_actual", "password_nueva")
    @classmethod
    def _validate_password_bytes(cls, v: str) -> str:
        return _check_password_bytes(v)


class CrearUsuarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    password: str = Field(min_length=1)

    @field_validator("email", "nombre")
    @classmethod
    def _strip_and_require_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("El campo no puede estar vacío.")
        return stripped

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, v: str) -> str:
        return _check_password_bytes(v)


class AsignarRolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: RolEnum
    vence_en: datetime | None = None

    @field_validator("vence_en")
    @classmethod
    def _validate_vence_en_utc_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("La fecha de vencimiento debe incluir zona horaria.")
        v_utc = v.astimezone(timezone.utc)
        if v_utc <= datetime.now(timezone.utc):
            raise ValueError("La fecha de vencimiento debe estar en el futuro.")
        return v_utc


class LoginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mensaje: str
    debe_cambiar_password: bool
    expira_en_segundos: int


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: str
    activo: bool
    debe_cambiar_password: bool
    roles: list[str] = Field(default_factory=list)
    roles_token: list[str] = Field(default_factory=list)

    @field_validator("roles", mode="before")
    @classmethod
    def _coerce_roles(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, (list, tuple, set)):
            return [str(getattr(item, "rol", item)) for item in v]
        return []


class AsignacionRolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    rol: str
    desde: datetime
    vence_en: datetime | None = None
    revocada_en: datetime | None = None
    otorgada_por: int | None = None


class EventoSeguridadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cuando: datetime
    actor: str
    accion: str
