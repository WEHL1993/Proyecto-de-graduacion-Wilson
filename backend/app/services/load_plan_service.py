"""Caso de uso: planificación de carga de ruta (ADR-06, ADR-07; TC-LOAD-01..04).

Estados: `borrador → pendiente_aprobacion → aprobada | rechazada → despachada`. No existe una
acción API para «enviar» (borrador → pendiente_aprobacion), por lo que aprobar y rechazar se
aceptan desde ambos estados. Rechazar también se acepta sobre una carga `aprobada` aún no
despachada: libera sus reservas. Nada se despacha automáticamente.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import EstadoCarga
from app.domain.models.operations import CargaRuta
from app.repositories import carga_repo, catalog_repo, sales_repo
from app.schemas.predictions import DemandRequest
from app.schemas.routes import LoadPlanItem, LoadPlanRequest, LoadPlanResponse
from app.services import inventory_service, prediction_service

_CENTESIMA = Decimal("0.01")
_MAX_PRODUCTOS_POR_PREDICCION = 200
_ESTADOS_DECIDIBLES = (EstadoCarga.BORRADOR, EstadoCarga.PENDIENTE_APROBACION)


def gestionar(db: Session, solicitud: LoadPlanRequest, usuario_id: uuid.UUID) -> LoadPlanResponse:
    if solicitud.accion == "generar":
        return generar(db, solicitud, usuario_id)
    if solicitud.accion == "aprobar":
        return aprobar(db, solicitud, usuario_id)
    return rechazar(db, solicitud, usuario_id)


# ------------------------------------------------------------------ generar
def generar(db: Session, solicitud: LoadPlanRequest, usuario_id: uuid.UUID) -> LoadPlanResponse:
    ruta_id, fecha = solicitud.ruta_id, solicitud.fecha_operacion
    assert ruta_id is not None and fecha is not None  # garantizado por LoadPlanRequest

    if not catalog_repo.ruta_existe(db, ruta_id):
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta indicada no existe.")
    if carga_repo.vigente_de_ruta(db, ruta_id, fecha) is not None:
        raise _carga_vigente_existente()
    producto_ids = sales_repo.productos_de_ruta(db, ruta_id)
    if not producto_ids:
        raise AppError("RUTA_SIN_PRODUCTOS", "La ruta no tiene productos con historial de ventas.")

    modelo_id, predicha = _predecir_demanda(db, producto_ids, ruta_id, fecha)
    disponible = inventory_service.stock_disponible(db, producto_ids)

    detalles = []
    for pid in producto_ids:
        demanda = predicha.get(pid, Decimal("0.00"))
        # ADR-07: el stock disponible prevalece sobre la demanda predicha.
        sugerida = min(demanda, disponible[pid])
        detalles.append(
            {
                "producto_id": pid,
                "cantidad_predicha": demanda,
                "stock_disponible_al_generar": disponible[pid],
                "cantidad_sugerida": sugerida,
                "ajustado_por_stock": sugerida < demanda,
            }
        )

    try:
        carga = carga_repo.crear(
            db,
            cabecera={
                "ruta_id": ruta_id,
                "fecha_operacion": fecha,
                "estado": EstadoCarga.BORRADOR,
                "modelo_id": modelo_id,
                "generado_por": usuario_id,
                "observaciones": solicitud.observaciones,
            },
            detalles=detalles,
        )
    except IntegrityError as exc:  # carrera con otra generación: lo decide el índice único parcial
        db.rollback()
        raise _carga_vigente_existente() from exc

    alertas = inventory_service.evaluar_cobertura(
        db,
        {pid: (predicha.get(pid, Decimal("0.00")), disponible[pid]) for pid in producto_ids},
        modelo_id=modelo_id,
        contexto=f"plan de carga del {fecha.isoformat()}",
    )
    db.commit()
    return _respuesta(db, carga, alertas)


def _predecir_demanda(
    db: Session, producto_ids: list[uuid.UUID], ruta_id: uuid.UUID, fecha_operacion: date
) -> tuple[uuid.UUID, dict[uuid.UUID, Decimal]]:
    """Demanda de `fecha_operacion` por producto: horizonte 1 desde el día anterior."""
    demanda: dict[uuid.UUID, Decimal] = {}
    modelo_id: uuid.UUID | None = None
    for i in range(0, len(producto_ids), _MAX_PRODUCTOS_POR_PREDICCION):
        respuesta = prediction_service.predecir_demanda(
            db,
            DemandRequest(
                producto_ids=producto_ids[i : i + _MAX_PRODUCTOS_POR_PREDICCION],
                ruta_id=ruta_id,
                fecha_base=fecha_operacion - timedelta(days=1),
                horizonte_dias=1,
                incluir_intervalo=False,
            ),
        )
        modelo_id = respuesta.modelo.id
        for pron in respuesta.pronosticos:
            valor = Decimal(str(pron.serie[0].demanda_predicha))
            demanda[pron.producto_id] = max(Decimal(0), valor).quantize(_CENTESIMA)
    assert modelo_id is not None
    return modelo_id, demanda


# ------------------------------------------------------------------ aprobar
def aprobar(db: Session, solicitud: LoadPlanRequest, usuario_id: uuid.UUID) -> LoadPlanResponse:
    carga = _cargar_para_decidir(db, solicitud.carga_id, _ESTADOS_DECIDIBLES, "aprobar")
    detalles = {d.producto_id: d for d in carga.detalles}

    ajustes = {a.producto_id: a.cantidad_aprobada for a in solicitud.ajustes or []}
    ajenos = set(ajustes) - set(detalles)
    if ajenos:
        raise AppError(
            "PRODUCTO_FUERA_DE_CARGA",
            "Hay ajustes para productos que no pertenecen a la carga.",
            detalle={"producto_ids": sorted(str(p) for p in ajenos)},
        )

    aprobadas = {pid: ajustes.get(pid, d.cantidad_sugerida) for pid, d in detalles.items()}
    excedidos = {
        str(pid): {
            "cantidad_aprobada": str(q),
            "stock_disponible_al_generar": str(detalles[pid].stock_disponible_al_generar),
        }
        for pid, q in aprobadas.items()
        if q > detalles[pid].stock_disponible_al_generar
    }
    if excedidos:
        raise AppError(
            "CANTIDAD_EXCEDE_STOCK",
            "La cantidad aprobada excede el stock disponible.",
            detalle={"productos": excedidos},
        )

    # Revalida contra el stock de hoy (otra carga pudo reservar desde que se generó). Falla
    # con CANTIDAD_EXCEDE_STOCK antes de modificar nada.
    inventory_service.reservar(db, aprobadas, referencia_id=carga.id, usuario_id=usuario_id)

    for pid, cantidad in aprobadas.items():
        detalles[pid].cantidad_aprobada = cantidad
    carga.estado = EstadoCarga.APROBADA
    carga.aprobado_por = usuario_id
    carga.aprobada_en = datetime.now(UTC)
    if solicitud.observaciones:
        carga.observaciones = solicitud.observaciones
    db.commit()
    return _respuesta(db, carga)


# ------------------------------------------------------------------ rechazar
def rechazar(db: Session, solicitud: LoadPlanRequest, usuario_id: uuid.UUID) -> LoadPlanResponse:
    carga = _cargar_para_decidir(
        db, solicitud.carga_id, (*_ESTADOS_DECIDIBLES, EstadoCarga.APROBADA), "rechazar"
    )
    if carga.estado == EstadoCarga.APROBADA:
        inventory_service.liberar(
            db,
            {d.producto_id: d.cantidad_aprobada or Decimal(0) for d in carga.detalles},
            referencia_id=carga.id,
            usuario_id=usuario_id,
        )
    notas = [carga.observaciones, solicitud.observaciones]
    motivo = f"Motivo de rechazo: {(solicitud.motivo_rechazo or '').strip()}"
    carga.observaciones = "\n".join(n for n in (*notas, motivo) if n)
    carga.estado = EstadoCarga.RECHAZADA
    db.commit()
    return _respuesta(db, carga)


# ------------------------------------------------------------------ utilidades
def _cargar_para_decidir(
    db: Session,
    carga_id: uuid.UUID | None,
    estados_validos: tuple[EstadoCarga, ...],
    accion: str,
) -> CargaRuta:
    assert carga_id is not None  # garantizado por LoadPlanRequest
    carga = carga_repo.obtener(db, carga_id, bloquear=True)
    if carga is None:
        raise AppError("CARGA_NO_ENCONTRADA", "La carga indicada no existe.")
    if carga.estado not in estados_validos:
        raise AppError(
            "ESTADO_CARGA_INVALIDO",
            f"No se puede {accion} una carga en estado `{carga.estado}`.",
            detalle={"estado": carga.estado, "estados_validos": [str(e) for e in estados_validos]},
        )
    return carga


def _carga_vigente_existente() -> AppError:
    return AppError(
        "CARGA_VIGENTE_EXISTENTE", "Ya existe una carga vigente para la ruta y fecha indicadas."
    )


def _respuesta(
    db: Session, carga: CargaRuta, alertas: list[uuid.UUID] | None = None
) -> LoadPlanResponse:
    skus = catalog_repo.skus_de(db, [d.producto_id for d in carga.detalles])
    items = [
        LoadPlanItem(
            producto_id=d.producto_id,
            sku=skus[d.producto_id],
            cantidad_predicha=d.cantidad_predicha,
            stock_disponible=d.stock_disponible_al_generar,
            cantidad_sugerida=d.cantidad_sugerida,
            cantidad_aprobada=d.cantidad_aprobada,
            ajustado_por_stock=d.ajustado_por_stock,
        )
        for d in sorted(carga.detalles, key=lambda d: skus[d.producto_id])
    ]
    return LoadPlanResponse(
        carga_id=carga.id,
        ruta_id=carga.ruta_id,
        fecha_operacion=carga.fecha_operacion,
        estado=EstadoCarga(carga.estado),
        modelo_id=carga.modelo_id,
        items=items,
        alertas_generadas=alertas or [],
    )
