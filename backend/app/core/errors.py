"""Excepción de negocio uniforme y su handler HTTP.

El contrato OpenAPI (`components.schemas.Error`) exige el cuerpo `{codigo, mensaje}` en
toda respuesta 400/401/403/500. `AppError` es la única forma en que `services/` y `api/`
deben señalar estos casos; el handler la traduce a `JSONResponse` sin exponer trazas.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        codigo: str,
        mensaje: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detalle: dict | None = None,
    ) -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        self.status_code = status_code
        self.detalle = detalle
        super().__init__(mensaje)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    cuerpo: dict[str, object] = {"codigo": exc.codigo, "mensaje": exc.mensaje}
    if exc.detalle is not None:
        cuerpo["detalle"] = exc.detalle
    return JSONResponse(status_code=exc.status_code, content=cuerpo)
