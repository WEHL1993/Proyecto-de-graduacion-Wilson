"""Bandeja de alertas por rol (`/alerts`) e historial de lotes ETL (`/etl/batches`)."""

import uuid
from types import SimpleNamespace

import pytest

from app.domain.enums import EstadoAlerta, EstadoLoteEtl, Severidad, TipoAlerta
from app.domain.models.ml import Alerta
from app.domain.models.sales import EtlLote

from .conftest import crear_usuario, encabezados

ALERTAS = "/api/v1/alerts"
LOTES = "/api/v1/etl/batches"

PERFILES = {
    "inventario": ("alertas:leer", "inventario:leer", "etl:cargar", "prediccion:consultar"),
    "bodega": ("alertas:leer", "inventario:leer", "inventario:ajustar"),
    "gerente": (
        "alertas:leer",
        "ml:metricas:leer",
        "prediccion:consultar",
        "liquidaciones:leer",
    ),
    "admin": (
        "alertas:leer",
        "inventario:leer",
        "etl:cargar",
        "prediccion:consultar",
        "ml:metricas:leer",
        "ml:reentrenar",
        "liquidaciones:leer",
    ),
    "sin_dominio": ("alertas:leer",),
}


@pytest.fixture
def entorno(db_tx, cliente):
    db = db_tx
    alertas = {
        tipo: Alerta(tipo=tipo, severidad=Severidad.ADVERTENCIA, mensaje=f"alerta {tipo}")
        for tipo in TipoAlerta
    }
    db.add_all(alertas.values())
    usuario = crear_usuario(db, "operador")
    db.commit()
    return SimpleNamespace(
        db=db,
        client=cliente,
        alertas=alertas,
        ids={str(a.id): tipo for tipo, a in alertas.items()},
        headers={
            nombre: encabezados(usuario, *permisos, roles=(nombre,))
            for nombre, permisos in PERFILES.items()
        },
        usuario=usuario,
    )


def _tipos_visibles(e, perfil: str) -> set[TipoAlerta]:
    r = e.client.get(ALERTAS, params={"limit": 100}, headers=e.headers[perfil])
    assert r.status_code == 200, r.text
    return {e.ids[a["id"]] for a in r.json()["alertas"] if a["id"] in e.ids}


# TC-ALE-01
def test_cada_rol_ve_solo_los_tipos_de_su_dominio(entorno):
    e = entorno
    assert _tipos_visibles(e, "admin") == set(TipoAlerta)
    assert _tipos_visibles(e, "inventario") == set(TipoAlerta) - {
        TipoAlerta.MAPE_UMBRAL,
        TipoAlerta.DIFERENCIA_CAJA,
    }
    assert _tipos_visibles(e, "bodega") == {TipoAlerta.STOCK_BAJO}
    assert _tipos_visibles(e, "gerente") == {
        TipoAlerta.MAPE_UMBRAL,
        TipoAlerta.QUIEBRE_PROYECTADO,
        TipoAlerta.DIFERENCIA_CAJA,  # ADR-14: Administrador y Gerente atienden el cuadre de caja
    }
    assert _tipos_visibles(e, "sin_dominio") == set()
    sin_permiso = encabezados(e.usuario, "inventario:leer")
    assert e.client.get(ALERTAS, headers=sin_permiso).status_code == 403
    assert e.client.get(ALERTAS).status_code == 401


# TC-ALE-01
def test_total_refleja_el_filtro_por_rol(entorno):
    e = entorno
    vacio = e.client.get(ALERTAS, headers=e.headers["sin_dominio"]).json()
    assert vacio == {"total": 0, "alertas": []}


# TC-ALE-02
def test_reconocer_alerta_la_saca_de_la_bandeja_abierta(entorno):
    e = entorno
    alerta = e.alertas[TipoAlerta.STOCK_BAJO]
    r = e.client.patch(f"{ALERTAS}/{alerta.id}/acknowledge", headers=e.headers["bodega"])
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == EstadoAlerta.RECONOCIDA
    assert TipoAlerta.STOCK_BAJO not in _tipos_visibles(e, "bodega")

    repetida = e.client.patch(f"{ALERTAS}/{alerta.id}/acknowledge", headers=e.headers["bodega"])
    assert repetida.status_code == 409 and repetida.json()["codigo"] == "ALERTA_NO_ABIERTA"

    reconocidas = e.client.get(
        ALERTAS, params={"estado": "reconocida", "limit": 100}, headers=e.headers["bodega"]
    ).json()
    assert str(alerta.id) in {a["id"] for a in reconocidas["alertas"]}


# TC-ALE-03
def test_no_reconoce_alertas_ajenas_al_rol_ni_inexistentes(entorno):
    e = entorno
    ajena = e.alertas[TipoAlerta.MAPE_UMBRAL]
    r = e.client.patch(f"{ALERTAS}/{ajena.id}/acknowledge", headers=e.headers["bodega"])
    assert r.status_code == 404 and r.json()["codigo"] == "ALERTA_NO_ENCONTRADA"
    e.db.refresh(ajena)
    assert ajena.estado == EstadoAlerta.ABIERTA
    inexistente = e.client.patch(
        f"{ALERTAS}/{uuid.uuid4()}/acknowledge", headers=e.headers["inventario"]
    )
    assert inexistente.status_code == 404
    sin_permiso = encabezados(e.usuario, "inventario:leer")
    assert (
        e.client.patch(f"{ALERTAS}/{ajena.id}/acknowledge", headers=sin_permiso).status_code == 403
    )


# ------------------------------------------------------------------ lotes ETL
def _lote(e, estado, validas, rechazadas):
    lote = EtlLote(
        usuario_id=e.usuario.id,
        archivo_nombre=f"{estado}-{uuid.uuid4().hex[:6]}.xlsx",
        checksum_sha256=uuid.uuid4().hex * 2,
        estado=estado,
        filas_totales=validas + rechazadas,
        filas_validas=validas,
        filas_rechazadas=rechazadas,
    )
    e.db.add(lote)
    e.db.commit()
    return lote


# TC-ALE-04
def test_historial_de_lotes_con_filtro_y_paginacion(entorno):
    e = entorno
    cargado = _lote(e, EstadoLoteEtl.CARGADO, 100, 3)
    rechazado = _lote(e, EstadoLoteEtl.RECHAZADO, 0, 12)

    r = e.client.get(LOTES, params={"limit": 200}, headers=e.headers["inventario"])
    assert r.status_code == 200, r.text
    por_id = {lote["id"]: lote for lote in r.json()["lotes"]}
    fila = por_id[str(cargado.id)]
    assert (fila["filas_totales"], fila["filas_validas"], fila["filas_rechazadas"]) == (103, 100, 3)
    assert fila["estado"] == "cargado" and fila["cargado_por"] == "operador"
    assert por_id[str(rechazado.id)]["estado"] == "rechazado"

    solo_rechazados = e.client.get(
        LOTES, params={"estado": "rechazado", "limit": 200}, headers=e.headers["inventario"]
    ).json()
    assert {x["estado"] for x in solo_rechazados["lotes"]} == {"rechazado"}
    assert str(rechazado.id) in {x["id"] for x in solo_rechazados["lotes"]}

    pagina = e.client.get(LOTES, params={"limit": 1}, headers=e.headers["inventario"]).json()
    assert len(pagina["lotes"]) == 1 and pagina["total"] >= 2


# TC-ALE-04
def test_historial_de_lotes_exige_permiso_de_carga(entorno):
    e = entorno
    assert e.client.get(LOTES).status_code == 401
    assert e.client.get(LOTES, headers=e.headers["gerente"]).status_code == 403
