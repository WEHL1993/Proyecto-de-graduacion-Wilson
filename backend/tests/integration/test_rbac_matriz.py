"""RBAC en la BD (ADR-19): permisos en vivo, matriz editable y pantallas autorizadas."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.domain.models.auth import Permiso, Rol

from .conftest import crear_usuario, encabezados

pytestmark = pytest.mark.rbac_vivo

BASE = "/api/v1/rbac"
ME = "/api/v1/auth/me"


def _rol(db, nombre: str) -> Rol:
    return db.scalar(select(Rol).where(Rol.nombre == nombre))


@pytest.fixture
def e(db_tx, cliente):
    db = db_tx
    admin = crear_usuario(db, "admin-rbac")
    admin.roles = [_rol(db, "Administrador")]
    # Rol propio por prueba: nunca se toca la matriz real de los roles sembrados.
    rol = Rol(nombre=f"Prueba-{uuid.uuid4().hex[:6]}", descripcion="rol de prueba")
    db.add(rol)
    db.flush()
    rol.permisos = list(db.scalars(select(Permiso).where(Permiso.codigo == "inventario:leer")))
    otro = crear_usuario(db, "usuario-rbac")
    otro.roles = [rol]
    db.commit()
    return SimpleNamespace(
        db=db,
        client=cliente,
        admin=admin,
        rol=rol,
        otro=otro,
        h=encabezados(admin),  # permisos del token: irrelevantes, se leen de la BD
        h_otro=encabezados(otro),
    )


def _permisos(e, *codigos: str):
    return e.client.put(
        f"{BASE}/roles/{e.rol.id}/permissions", json={"permisos": list(codigos)}, headers=e.h
    )


def test_los_permisos_salen_de_la_bd_y_no_del_token(e):
    # El token de `otro` no declara permisos, pero su rol sí tiene inventario:leer en la BD.
    me = e.client.get(ME, headers=e.h_otro).json()
    assert me["permisos"] == ["inventario:leer"]
    assert {p["clave"] for p in me["menu"]} == {"inventario", "productos"}
    assert me["pantalla_inicio"] == "/inventario"
    # Y un token inflado no concede nada: lo que vale es la BD.
    falso = encabezados(e.otro, "usuarios:gestionar", "roles:gestionar")
    assert e.client.get(f"{BASE}/matrix", headers=falso).status_code == 403


def test_quitar_un_permiso_surte_efecto_de_inmediato(e):
    assert e.client.get(ME, headers=e.h_otro).status_code == 200
    r = _permisos(e)
    assert r.status_code == 200 and r.json()["permisos"] == []
    me = e.client.get(ME, headers=e.h_otro).json()
    assert me["permisos"] == [] and me["menu"] == [] and me["pantalla_inicio"] is None


def test_asignar_permisos_cambia_el_menu(e):
    assert _permisos(e, "reportes:leer", "liquidaciones:leer").status_code == 200
    claves = [p["clave"] for p in e.client.get(ME, headers=e.h_otro).json()["menu"]]
    assert claves == ["liquidaciones", "reportes"]  # en orden de menú


def test_permiso_inexistente_y_rol_inexistente(e):
    r = _permisos(e, "x:y")
    assert r.status_code == 400 and r.json()["codigo"] == "PERMISO_INVALIDO"
    r = e.client.put(f"{BASE}/roles/32000/permissions", json={"permisos": []}, headers=e.h)
    assert r.status_code == 404 and r.json()["codigo"] == "ROL_NO_ENCONTRADO"


def test_el_rol_de_sistema_esta_protegido(e):
    admin = _rol(e.db, "Administrador")
    r = e.client.put(f"{BASE}/roles/{admin.id}/permissions", json={"permisos": []}, headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "ROL_SISTEMA_PROTEGIDO"
    r = e.client.patch(f"{BASE}/roles/{admin.id}", json={"activo": False}, headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "ROL_SISTEMA_PROTEGIDO"


def test_desactivar_un_rol_retira_el_acceso_sin_dejar_usuarios_huerfanos(e):
    # Único rol de un usuario activo: se rechaza.
    r = e.client.patch(f"{BASE}/roles/{e.rol.id}", json={"activo": False}, headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "ROL_CON_USUARIOS"
    # Con otro rol activo disponible, se puede y el permiso del rol desactivado deja de valer.
    e.otro.roles = [e.rol, _rol(e.db, "Liquidador")]
    e.db.commit()
    r = e.client.patch(f"{BASE}/roles/{e.rol.id}", json={"activo": False}, headers=e.h)
    assert r.status_code == 200 and r.json()["activo"] is False
    me = e.client.get(ME, headers=e.h_otro).json()
    assert "inventario:leer" not in me["permisos"] and me["roles"] == ["Liquidador"]
    # Reactivar devuelve el acceso.
    e.client.patch(f"{BASE}/roles/{e.rol.id}", json={"activo": True}, headers=e.h)
    assert "inventario:leer" in e.client.get(ME, headers=e.h_otro).json()["permisos"]


def test_un_usuario_desactivado_pierde_la_sesion_aunque_su_token_siga_vigente(e):
    e.otro.activo = False
    e.db.commit()
    r = e.client.get(ME, headers=e.h_otro)
    assert r.status_code == 401 and r.json()["codigo"] == "SESION_INVALIDA"


def test_pantalla_de_inicio_configurable_por_rol(e):
    _permisos(e, "inventario:leer", "reportes:leer")
    url = f"{BASE}/roles/{e.rol.id}"
    r = e.client.patch(url, json={"pantalla_inicio": "reportes"}, headers=e.h)
    assert r.status_code == 200 and r.json()["pantalla_inicio"] == "reportes"
    assert e.client.get(ME, headers=e.h_otro).json()["pantalla_inicio"] == "/reportes"
    r = e.client.patch(f"{BASE}/roles/{e.rol.id}", json={"pantalla_inicio": "nada"}, headers=e.h)
    assert r.status_code == 400 and r.json()["codigo"] == "PANTALLA_INVALIDA"
    r = e.client.patch(f"{BASE}/roles/{e.rol.id}", json={"pantalla_inicio": None}, headers=e.h)
    assert r.json()["pantalla_inicio"] is None


def test_la_matriz_expone_roles_permisos_y_pantallas_de_la_bd(e):
    m = e.client.get(f"{BASE}/matrix", headers=e.h).json()
    roles = {r["nombre"]: r for r in m["roles"]}
    assert {"Administrador", "Gerente", "Liquidador"} <= roles.keys()
    assert roles["Administrador"]["es_sistema"] and roles["Administrador"]["activo"]
    assert "roles:gestionar" in roles["Administrador"]["permisos"]
    assert roles[e.rol.nombre]["total_usuarios"] == 1
    assert {p["codigo"] for p in m["permisos"]} >= {"inventario:leer", "roles:gestionar"}
    pantallas = {p["clave"]: p for p in m["pantallas"]}
    assert len(pantallas) >= 12
    assert set(pantallas["compras"]["permisos"]) == {
        "pedido_proveedor:gestionar",
        "pedido_proveedor:confirmar",
        "inventario:ajustar",
    }


def test_acceso_de_un_usuario_muestra_por_que_ve_cada_pantalla(e):
    a = e.client.get(f"{BASE}/users/{e.otro.id}/access", headers=e.h).json()
    por_clave = {p["clave"]: p for p in a["pantallas"]}
    assert por_clave["inventario"]["autorizada"]
    assert por_clave["inventario"]["via_permisos"] == ["inventario:leer"]
    assert not por_clave["usuarios"]["autorizada"]
    assert e.client.get(f"{BASE}/users/{uuid.uuid4()}/access", headers=e.h).status_code == 404


def test_el_login_devuelve_el_menu_de_la_bd(e):
    r = e.client.post(
        "/api/v1/auth/login", json={"email": e.otro.email, "password": "ClaveSegura123"}
    )
    assert r.status_code == 200
    u = r.json()["usuario"]
    assert u["permisos"] == ["inventario:leer"]
    assert [p["clave"] for p in u["menu"]] == ["inventario", "productos"]
