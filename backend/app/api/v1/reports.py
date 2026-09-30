"""Reportes gerenciales (`/reports`). Sin reglas de negocio: delega en `report_service`.
Todo el módulo exige `reportes:leer`."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.reports import (
    ComisionReporte,
    FormatoReporte,
    RotacionReporte,
    TipoReporte,
    VentasProyeccionReporte,
)
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])

Lee = Annotated[UsuarioAutenticado, Depends(require_permission("reportes:leer"))]

_RANGO = "Sin `desde`/`hasta` usa los últimos 30 días hasta la última venta registrada."


@router.get(
    "/inventory-turnover",
    response_model=RotacionReporte,
    summary="Rotación de inventario e índice de quiebres por ruta",
    description=(
        "Requiere `reportes:leer`. Rotación = costo de ventas del periodo / valor del inventario "
        "actual. Índice de quiebre = % de líneas de carga limitadas por stock "
        f"(`ajustado_por_stock`). {_RANGO}"
    ),
)
def rotacion(
    db: DBSession,
    _usuario: Lee,
    desde: date | None = None,
    hasta: date | None = None,
    ruta_id: UUID | None = None,
) -> RotacionReporte:
    return report_service.rotacion_e_indice_quiebres(db, desde, hasta, ruta_id)


@router.get(
    "/commissions",
    response_model=ComisionReporte,
    summary="Liquidación de comisiones por vendedor y periodo",
    description=(
        "Requiere `reportes:leer`. Agrupa `comisiones` sobre `ventas_historicas` por vendedor y "
        "periodo (`YYYY-MM`). Sin periodos usa el mes de la última actividad."
    ),
)
def comisiones(
    db: DBSession,
    _usuario: Lee,
    periodo_desde: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    periodo_hasta: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    vendedor_id: UUID | None = None,
    ruta_id: UUID | None = None,
) -> ComisionReporte:
    return report_service.liquidacion_comisiones(
        db, periodo_desde, periodo_hasta, vendedor_id, ruta_id
    )


@router.get(
    "/sales-vs-forecast",
    response_model=VentasProyeccionReporte,
    summary="Volumen de venta real vs. proyectado por ruta",
    description=(
        "Requiere `reportes:leer`. Unidades reales (`ventas_historicas`) frente a la proyección "
        "más reciente por producto/ruta/día (`pronosticos_demanda`). Sin `desde`/`hasta` usa los "
        "últimos 30 días hasta la última fecha con venta o proyección."
    ),
)
def ventas_vs_proyeccion(
    db: DBSession,
    _usuario: Lee,
    desde: date | None = None,
    hasta: date | None = None,
    ruta_id: UUID | None = None,
) -> VentasProyeccionReporte:
    return report_service.ventas_vs_proyeccion(db, desde, hasta, ruta_id)


@router.get(
    "/export",
    summary="Exportar reportes en CSV o Excel",
    description=(
        "Requiere `reportes:leer`. `tipo=consolidado` reúne los tres reportes (una hoja por "
        "reporte en Excel; secciones separadas en CSV)."
    ),
    responses={200: {"content": {"text/csv": {}, "application/octet-stream": {}}}},
)
def exportar(
    db: DBSession,
    _usuario: Lee,
    tipo: TipoReporte = TipoReporte.CONSOLIDADO,
    formato: FormatoReporte = FormatoReporte.XLSX,
    desde: date | None = None,
    hasta: date | None = None,
    periodo_desde: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    periodo_hasta: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    ruta_id: UUID | None = None,
) -> Response:
    contenido, media_type, nombre = report_service.exportar(
        db,
        tipo,
        formato,
        desde=desde,
        hasta=hasta,
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        ruta_id=ruta_id,
    )
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
