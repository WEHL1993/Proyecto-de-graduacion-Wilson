"""Endpoints ETL (`POST /etl/upload-excel`). Sin reglas de negocio: delega en `etl_service`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.deps import DBSession, require_permission
from app.domain.enums import EstadoLoteEtl
from app.schemas.auth import UsuarioAutenticado
from app.schemas.etl import (
    TAMANO_MAXIMO_BYTES,
    EtlConfig,
    EtlResult,
    EtlValidationError,
    LotePage,
    ModoCarga,
)
from app.services import etl_service

router = APIRouter(prefix="/etl", tags=["ETL"])

PuedeCargar = Annotated[UsuarioAutenticado, Depends(require_permission("etl:cargar"))]
PuedeConfigurar = Annotated[UsuarioAutenticado, Depends(require_permission("etl:configurar"))]


@router.post(
    "/upload-excel",
    response_model=EtlResult,
    summary="Ingesta de histórico de ventas desde Excel",
    description=(
        "Requiere permiso `etl:cargar`. Valida estructura, tipos y reglas de negocio. "
        "Si existen errores bloqueantes el lote se rechaza completo (modo estricto) salvo "
        "`modo=parcial`. Un archivo con checksum ya cargado devuelve 400 `LOTE_DUPLICADO`. "
        "Con el arranque cerrado (`GET /etl/config`) devuelve 409 `EXCEL_DESHABILITADO`."
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


@router.get(
    "/batches",
    response_model=LotePage,
    summary="Historial de lotes ETL",
    description=(
        "Requiere permiso `etl:cargar`. Auditoría de cargas: fecha, filas válidas/rechazadas y "
        "estado de cada lote, del más reciente al más antiguo."
    ),
)
def listar_lotes(
    db: DBSession,
    _usuario: PuedeCargar,
    estado: EstadoLoteEtl | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LotePage:
    return etl_service.listar_lotes(db, estado=estado, limit=limit, offset=offset)


@router.get(
    "/config",
    response_model=EtlConfig,
    summary="Política de datos del modelo",
    description=(
        "Requiere permiso `etl:cargar`. `carga_excel_habilitada=false` indica que el arranque "
        "está cerrado y las ventas nuevas entran solo por la liquidación diaria; "
        "`fuente_reentrenamiento` define qué ventas alimentan los reentrenamientos (ADR-14)."
    ),
)
def obtener_config(db: DBSession, _usuario: PuedeCargar) -> EtlConfig:
    return etl_service.obtener_config(db)


@router.put(
    "/config",
    response_model=EtlConfig,
    summary="Cierra o reabre el arranque y fija la fuente de reentrenamiento",
    description="Requiere permiso `etl:configurar` (Administrador). Cambio auditado.",
)
def actualizar_config(db: DBSession, usuario: PuedeConfigurar, config: EtlConfig) -> EtlConfig:
    return etl_service.actualizar_config(db, config, usuario.id)
