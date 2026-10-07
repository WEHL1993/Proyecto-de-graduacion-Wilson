"""Equipo de ruta (M02, ADR-18): integrantes, porcentaje de reparto y vigencia.

- `PUT` reemplaza el equipo: cierra las vigencias anteriores (nunca las borra) y exige que los
  porcentajes sumen exactamente 100,00 (un CHECK de fila no puede garantizarlo).
- Se permite un equipo sin vendedor; los informes lo señalan.
- `rutas.vendedor_id` (liquidación y cargas) se conserva sin cambios. El vendedor de la ruta y el
  del equipo son dos fuentes de verdad que NO se sincronizan (se resuelve en M05/M06): solo se
  rechaza una contradicción explícita entre usuarios (`VENDEDOR_INCOHERENTE`).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import RolEnRuta
from app.domain.models.catalog import EquipoRuta, Ruta
from app.repositories import empleado_repo, equipo_repo, ruta_repo
from app.schemas.equipos import (
    EquipoReemplazo,
    EquipoRutaOut,
    IntegranteOut,
    RutaDesalineada,
    RutaEquipoIncompleto,
)
from app.services.bitacora_service import auditar

TOTAL = Decimal("100.00")
CERO = Decimal("0.00")


# ------------------------------------------------------------------ helpers puros
def suma_porcentajes(filas) -> Decimal:
    return sum((Decimal(f.porcentaje_reparto) for f in filas), CERO)


def motivos_incompleto(filas) -> list[str]:
    """Motivos por los que un equipo vigente está incompleto (vacío si está correcto)."""
    if not filas:
        return ["sin_equipo"]
    motivos = []
    if not any(f.rol_en_ruta == RolEnRuta.VENDEDOR for f in filas):
        motivos.append("sin_vendedor")
    if suma_porcentajes(filas) != TOTAL:
        motivos.append("suma_distinta_de_100")
    return motivos


def validar_vendedor_coherente(
    vendedor_ruta: uuid.UUID | None, usuario_empleado: uuid.UUID | None, empleado: str
) -> None:
    """409 si la ruta y el empleado vendedor apuntan a usuarios distintos (ambos definidos)."""
    if (
        vendedor_ruta is not None
        and usuario_empleado is not None
        and vendedor_ruta != usuario_empleado
    ):
        raise AppError(
            "VENDEDOR_INCOHERENTE",
            f"El usuario vinculado a «{empleado}» no coincide con el vendedor de la ruta "
            "(`rutas.vendedor_id`). Alinee ambos antes de guardar.",
            status_code=409,
            detalle={
                "vendedor_id_ruta": str(vendedor_ruta),
                "usuario_id_empleado": str(usuario_empleado),
            },
        )


def _hoy() -> date:
    return datetime.now(UTC).date()


def _ruta(db: Session, ruta_id: uuid.UUID, *, bloquear: bool = False) -> Ruta:
    ruta = ruta_repo.obtener(db, ruta_id, bloquear=bloquear)
    if ruta is None:
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta no existe.", status_code=404)
    return ruta


def _integrante_out(fila: EquipoRuta, nombres: dict[uuid.UUID, str]) -> IntegranteOut:
    return IntegranteOut(
        empleado_id=fila.empleado_id,
        nombre_completo=nombres.get(fila.empleado_id, ""),
        rol_en_ruta=RolEnRuta(fila.rol_en_ruta),
        porcentaje_reparto=fila.porcentaje_reparto,
        vigente_desde=fila.vigente_desde,
        vigente_hasta=fila.vigente_hasta,
    )


def _dto(db: Session, ruta_id: uuid.UUID) -> EquipoRutaOut:
    vigentes = equipo_repo.vigentes_de(db, ruta_id)
    historial = equipo_repo.historial_de(db, ruta_id)
    empleados = empleado_repo.obtener_varios(db, {f.empleado_id for f in [*vigentes, *historial]})
    nombres = {eid: e.nombre_completo for eid, e in empleados.items()}
    suma = suma_porcentajes(vigentes)
    return EquipoRutaOut(
        ruta_id=ruta_id,
        integrantes=[_integrante_out(f, nombres) for f in vigentes],
        suma_porcentaje=suma,
        suma_100=bool(vigentes) and suma == TOTAL,
        tiene_vendedor=any(f.rol_en_ruta == RolEnRuta.VENDEDOR for f in vigentes),
        historial=[_integrante_out(f, nombres) for f in historial],
    )


# ------------------------------------------------------------------ consulta
@auditar
def obtener(db: Session, ruta_id: uuid.UUID) -> EquipoRutaOut:
    _ruta(db, ruta_id)
    return _dto(db, ruta_id)


@auditar
def rutas_con_equipo_incompleto(db: Session) -> list[RutaEquipoIncompleto]:
    """Rutas activas sin equipo, sin vendedor o cuyo equipo vigente no suma 100."""
    rutas = ruta_repo.listar(db, activa=True)
    equipos = equipo_repo.vigentes_de_rutas(db, {r.id for r in rutas})
    informe = []
    for ruta in rutas:
        filas = equipos[ruta.id]
        motivos = motivos_incompleto(filas)
        if motivos:
            informe.append(
                RutaEquipoIncompleto(
                    ruta_id=ruta.id,
                    codigo=ruta.codigo,
                    nombre=ruta.nombre,
                    integrantes=len(filas),
                    suma_porcentaje=suma_porcentajes(filas),
                    tiene_vendedor="sin_vendedor" not in motivos and bool(filas),
                    motivos=motivos,
                )
            )
    return informe


@auditar
def rutas_desalineadas(db: Session) -> list[RutaDesalineada]:
    """Rutas cuyo `vendedor_id` difiere del `usuario_id` del empleado vendedor del equipo.

    Incluye el caso en que solo uno de los dos está definido (no hay contradicción, pero sí dos
    fuentes de verdad por reconciliar).
    """
    informe = []
    for ruta, empleado in equipo_repo.vendedores_vigentes(db):
        if ruta.vendedor_id != empleado.usuario_id:
            informe.append(
                RutaDesalineada(
                    ruta_id=ruta.id,
                    codigo=ruta.codigo,
                    nombre=ruta.nombre,
                    vendedor_id_ruta=ruta.vendedor_id,
                    empleado_vendedor_id=empleado.id,
                    empleado_vendedor=empleado.nombre_completo,
                    usuario_id_empleado=empleado.usuario_id,
                )
            )
    return informe


# ------------------------------------------------------------------ escritura
def _validar_solicitud(db: Session, ruta: Ruta, datos: EquipoReemplazo) -> None:
    ids = [i.empleado_id for i in datos.integrantes]
    if len(set(ids)) != len(ids):
        raise AppError("EMPLEADO_REPETIDO", "Un empleado no puede repetirse en el equipo.")
    vendedores = [i for i in datos.integrantes if i.rol_en_ruta == RolEnRuta.VENDEDOR]
    if len(vendedores) > 1:
        raise AppError("VENDEDOR_MULTIPLE", "La ruta admite como máximo un vendedor vigente.")

    suma = sum((i.porcentaje_reparto for i in datos.integrantes), CERO)
    if suma != TOTAL:
        raise AppError(
            "EQUIPO_NO_SUMA_100",
            f"Los porcentajes de reparto deben sumar 100,00 (suman {suma}).",
            detalle={"suma": str(suma)},
        )

    empleados = empleado_repo.obtener_varios(db, ids)
    for i in datos.integrantes:
        empleado = empleados.get(i.empleado_id)
        if empleado is None:
            raise AppError(
                "EMPLEADO_NO_ENCONTRADO",
                "Uno de los empleados indicados no existe.",
                status_code=404,
                detalle={"empleado_id": str(i.empleado_id)},
            )
        if not empleado.activo:
            raise AppError(
                "EMPLEADO_INACTIVO",
                f"El empleado «{empleado.nombre_completo}» está dado de baja.",
                status_code=409,
            )
    if vendedores:
        v = empleados[vendedores[0].empleado_id]
        validar_vendedor_coherente(ruta.vendedor_id, v.usuario_id, v.nombre_completo)


@auditar
def reemplazar(
    db: Session, ruta_id: uuid.UUID, datos: EquipoReemplazo, actor_id: uuid.UUID
) -> EquipoRutaOut:
    ruta = _ruta(db, ruta_id, bloquear=True)
    if not ruta.activa:
        raise AppError("RUTA_INACTIVA", "La ruta está desactivada.", status_code=409)
    _validar_solicitud(db, ruta, datos)

    desde = datos.vigente_desde or _hoy()
    vigentes = equipo_repo.vigentes_de(db, ruta_id)
    if vigentes and desde < max(f.vigente_desde for f in vigentes):
        raise AppError(
            "VIGENCIA_INVALIDA",
            "La nueva vigencia no puede ser anterior al inicio del equipo vigente.",
            detalle={"vigente_desde_actual": str(max(f.vigente_desde for f in vigentes))},
        )

    try:
        equipo_repo.cerrar(db, vigentes, desde - timedelta(days=1))
        for i in datos.integrantes:
            equipo_repo.agregar(
                db,
                ruta_id=ruta_id,
                empleado_id=i.empleado_id,
                rol_en_ruta=i.rol_en_ruta.value,
                porcentaje_reparto=i.porcentaje_reparto,
                vigente_desde=desde,
            )
        db.commit()
    except IntegrityError as exc:  # la fila de la ruta está bloqueada: solo una condición rara
        db.rollback()
        raise AppError(
            "EQUIPO_CONFLICTO", "El equipo cambió mientras se guardaba; reintente.", status_code=409
        ) from exc
    return _dto(db, ruta_id)
