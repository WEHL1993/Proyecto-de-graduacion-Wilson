"""M02 sin BD: guardas RBAC de `/catalog/*` y `/employees`, DTOs, matriz y reglas puras."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.seeds.seed_rbac import MATRIZ_ROL_PERMISO, PERMISOS
from app.main import app
from app.schemas.equipos import EquipoReemplazo, IntegranteIn
from app.schemas.products import ProductoCreate, ProductoUpdate
from app.services import catalog_service, empleado_service, equipo_service, ruta_service
from app.services.equipo_service import (
    motivos_incompleto,
    suma_porcentajes,
    validar_vendedor_coherente,
)

RID = uuid.uuid4()
EID = uuid.uuid4()
CAT = "/api/v1/catalog"
EMP = "/api/v1/employees"
EQUIPO = {
    "integrantes": [
        {"empleado_id": str(EID), "rol_en_ruta": "vendedor", "porcentaje_reparto": "100"}
    ]
}

# (método, ruta, cuerpo, permiso requerido)
RUTAS = [
    ("GET", f"{CAT}/routes/admin", None, "catalogos:leer"),
    ("GET", f"{CAT}/routes/{RID}", None, "catalogos:leer"),
    ("GET", f"{CAT}/routes/{RID}/team", None, "catalogos:leer"),
    ("GET", f"{CAT}/teams/incomplete", None, "catalogos:leer"),
    ("GET", f"{CAT}/teams/misaligned", None, "catalogos:leer"),
    ("GET", EMP, None, "catalogos:leer"),
    ("GET", f"{EMP}/{EID}", None, "catalogos:leer"),
    ("POST", f"{CAT}/routes", {"codigo": "X", "nombre": "Ruta X"}, "catalogos:gestionar"),
    ("PATCH", f"{CAT}/routes/{RID}", {"zona": "Norte"}, "catalogos:gestionar"),
    ("POST", f"{CAT}/routes/{RID}/deactivate", None, "catalogos:gestionar"),
    ("POST", f"{CAT}/routes/{RID}/activate", None, "catalogos:gestionar"),
    ("PUT", f"{CAT}/routes/{RID}/team", EQUIPO, "catalogos:gestionar"),
    ("POST", EMP, {"nombre_completo": "Ana Pérez"}, "catalogos:gestionar"),
    ("PATCH", f"{EMP}/{EID}", {"nombre_completo": "Ana P."}, "catalogos:gestionar"),
    ("DELETE", f"{EMP}/{EID}", None, "catalogos:gestionar"),
    ("POST", f"{EMP}/{EID}/reactivate", None, "catalogos:gestionar"),
]


def _headers(*permisos: str) -> dict[str, str]:
    token, _ = create_access_token(sub=str(uuid.uuid4()), roles=[], perms=list(permisos))
    return {"Authorization": f"Bearer {token}"}


class _Salida:
    """Respuesta que FastAPI no puede validar: solo interesa el flujo hasta el servicio."""


@pytest.fixture
def cliente(monkeypatch):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    for modulo, nombres in (
        (ruta_service, ("listar", "obtener", "crear", "actualizar", "desactivar", "activar")),
        (
            equipo_service,
            ("obtener", "reemplazar", "rutas_con_equipo_incompleto", "rutas_desalineadas"),
        ),
        (empleado_service, ("listar", "obtener", "crear", "actualizar", "reactivar")),
    ):
        for nombre in nombres:
            monkeypatch.setattr(modulo, nombre, lambda *a, **k: _Salida())
    monkeypatch.setattr(empleado_service, "dar_de_baja", lambda *a, **k: None)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permiso"), RUTAS)
def test_sin_token_responde_401(cliente, metodo, ruta, cuerpo, permiso):
    r = cliente.request(metodo, ruta, json=cuerpo)
    assert r.status_code == 401 and r.json()["codigo"] == "NO_AUTENTICADO"


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permiso"), RUTAS)
def test_sin_el_permiso_responde_403(cliente, metodo, ruta, cuerpo, permiso):
    otros = [p for p in PERMISOS if p != permiso]
    r = cliente.request(metodo, ruta, json=cuerpo, headers=_headers(*otros))
    assert r.status_code == 403 and permiso in r.json()["mensaje"]


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permiso"), RUTAS)
def test_con_el_permiso_pasa_la_guarda(cliente, metodo, ruta, cuerpo, permiso):
    r = cliente.request(metodo, ruta, json=cuerpo, headers=_headers(permiso))
    assert r.status_code not in (401, 403, 404, 422)


def test_leer_no_basta_para_gestionar(cliente):
    r = cliente.post(
        f"{CAT}/routes",
        json={"codigo": "X", "nombre": "Ruta X"},
        headers=_headers("catalogos:leer"),
    )
    assert r.status_code == 403


@pytest.mark.parametrize("ruta", ["routes", "categories", "suppliers"])
def test_la_lectura_basica_sigue_abierta_a_cualquier_autenticado(cliente, monkeypatch, ruta):
    monkeypatch.setattr(catalog_service, "listar_rutas", lambda db: [])
    monkeypatch.setattr(catalog_service, "listar_categorias", lambda db: [])
    monkeypatch.setattr(catalog_service, "listar_proveedores", lambda db: [])
    assert cliente.get(f"{CAT}/{ruta}", headers=_headers()).status_code == 200


# ------------------------------------------------------------------ matriz de permisos
def test_matriz_de_permisos_de_catalogos():
    assert {"catalogos:leer", "catalogos:gestionar"} <= PERMISOS.keys()
    con_leer = {r for r, ps in MATRIZ_ROL_PERMISO.items() if "catalogos:leer" in ps}
    assert con_leer == {"Administrador", "Gerente", "EncargadoInventario"}
    con_gestionar = {r for r, ps in MATRIZ_ROL_PERMISO.items() if "catalogos:gestionar" in ps}
    assert con_gestionar == {"Administrador"}


# ------------------------------------------------------------------ DTOs
def test_producto_acepta_los_campos_de_paquete():
    p = ProductoCreate(
        sku="500179",
        nombre="BIG COLA",
        categoria_id=uuid.uuid4(),
        unidades_por_paquete=6,
        medida_ml=3030,
        sabor="COLA",
    )
    assert (p.unidades_por_paquete, p.medida_ml, p.sabor) == (6, 3030, "COLA")
    simple = ProductoCreate(sku="A", nombre="Nombre", categoria_id=uuid.uuid4())
    assert simple.unidades_por_paquete == 1 and simple.medida_ml is None


@pytest.mark.parametrize("campos", [{"unidades_por_paquete": 0}, {"medida_ml": 0}])
def test_producto_rechaza_paquete_o_medida_no_positivos(campos):
    with pytest.raises(ValidationError):
        ProductoCreate(sku="A", nombre="Nombre", categoria_id=uuid.uuid4(), **campos)
    with pytest.raises(ValidationError):
        ProductoUpdate(**campos)


@pytest.mark.parametrize("porcentaje", ["-1", "100.01"])
def test_porcentaje_fuera_de_rango_se_rechaza(porcentaje):
    with pytest.raises(ValidationError):
        IntegranteIn(empleado_id=EID, rol_en_ruta="vendedor", porcentaje_reparto=porcentaje)


def test_equipo_exige_al_menos_un_integrante():
    with pytest.raises(ValidationError):
        EquipoReemplazo(integrantes=[])


# ------------------------------------------------------------------ reglas puras
def _fila(rol, pct):
    return SimpleNamespace(rol_en_ruta=rol, porcentaje_reparto=Decimal(pct))


def test_equipo_completo_no_tiene_motivos():
    assert motivos_incompleto([_fila("vendedor", "60"), _fila("chofer", "40")]) == []


@pytest.mark.parametrize(
    ("filas", "motivos"),
    [
        ([], ["sin_equipo"]),
        ([_fila("chofer", "100")], ["sin_vendedor"]),
        ([_fila("vendedor", "50"), _fila("auxiliar", "49.99")], ["suma_distinta_de_100"]),
        (
            [_fila("chofer", "50"), _fila("auxiliar", "40")],
            ["sin_vendedor", "suma_distinta_de_100"],
        ),
    ],
)
def test_motivos_de_equipo_incompleto(filas, motivos):
    assert motivos_incompleto(filas) == motivos


def test_suma_usa_decimales_exactos():
    filas = [_fila("a", "33.33"), _fila("b", "33.33"), _fila("c", "33.34")]
    assert suma_porcentajes(filas) == Decimal("100.00")


def test_vendedor_coherente_solo_rechaza_contradicciones_explicitas():
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    validar_vendedor_coherente(None, u1, "Ana")  # la ruta no tiene vendedor
    validar_vendedor_coherente(u1, None, "Ana")  # el empleado no tiene usuario
    validar_vendedor_coherente(u1, u1, "Ana")
    with pytest.raises(AppError) as exc:
        validar_vendedor_coherente(u1, u2, "Ana")
    assert exc.value.codigo == "VENDEDOR_INCOHERENTE" and exc.value.status_code == 409
