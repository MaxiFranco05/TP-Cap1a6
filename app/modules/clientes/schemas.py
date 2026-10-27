from pydantic import BaseModel, ConfigDict, Field


class CrearClienteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1)
    documento: str = Field(min_length=1)
    telefono: str = Field(min_length=1)


class CrearVehiculoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    patente: str = Field(min_length=1)
    marca: str = Field(min_length=1)
    modelo: str = Field(min_length=1)
    anio: int = Field(ge=1950, le=2100)


class VehiculoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    patente: str
    marca: str
    modelo: str
    anio: int


class ClienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int | None = None
    nombre: str
    documento: str
    telefono: str
    vehiculos: list[VehiculoResponse] = Field(default_factory=list)
