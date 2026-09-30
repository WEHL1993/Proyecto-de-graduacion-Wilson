"""Endpoints ETL (`POST /etl/upload-excel`). Sin reglas de negocio: delega en `etl_service`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.etl import (
    TAMANO_MAXIMO_BYTES,
    EtlResult,
    EtlValidationError,
    ModoCarga,
)
from app.services import etl_service

router = APIRouter(prefix="/etl", tags=["ETL"])

PuedeCargar = Annotated[UsuarioAutenticado, Depends(require_permission("etl:cargar"))]


@router.post(
    "/upload-excel",
    response_model=EtlResult,
    summary="Ingesta de histórico de ventas desde Excel",
    description=(
        "Requiere permiso `etl:cargar`. Valida estructura, tipos y reglas de negocio. "
        "Si existen errores bloqueantes el lote se rechaza completo (modo estricto) salvo "
        "`modo=parcial`. Un archivo con checksum ya cargado devuelve 400 `LOTE_DUPLICADO`."
    ),
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": EtlValidationError,
            "description": "El archivo no cumple validaciones estructurales o de datos",
        }
    },
)
def upload_excel(
    db: DBSession,
    usuario: PuedeCargar,
    file: UploadFile,
    modo: Annotated[ModoCarga, Form()] = ModoCarga.ESTRICTO,
    hoja: Annotated[
        str | None, Form(description="Nombre de la hoja; por defecto la primera")
    ] = None,
    periodo: Annotated[
        str | None,
        Form(
            description="YYYY-MM. Solo formato ancho; por defecto se infiere del nombre del archivo"
        ),
    ] = None,
) -> EtlResult | JSONResponse:
    contenido = file.file.read(TAMANO_MAXIMO_BYTES + 1)
    resultado = etl_service.procesar_excel(
        db,
        usuario_id=usuario.id,
        nombre_archivo=file.filename or "",
        contenido=contenido,
        modo=modo,
        hoja=hoja,
        periodo=periodo,
    )
    if isinstance(resultado, EtlValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=resultado.model_dump(mode="json", exclude_none=True),
        )
    return resultado
