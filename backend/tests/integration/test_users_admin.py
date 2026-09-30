"""CRUD administrativo de usuarios contra PostgreSQL real (`/users`, `usuarios:gestionar`)."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.domain.models.auth import Rol, Usuario
from app.domain.models.catalog import Ruta

from .conftest import crear_usuario, encabezados

BASE = "/api/v1/users"
LOGIN = "/api/v1/auth/login"


@pytest.fixture
def entorno(db_tx, cliente):
    db = db_tx
    for nombre in ("Admin", "Ventas", "Proveedor"):
        if db.scalar(select(Rol).where(Rol.nombre == nombre)) is None:
            db.add(Rol(nombre=nombre, descripcion=nombre))
    sufijo = uuid.uuid4().hex[:6]
    rutas = [
        Ruta(codigo=f"R1-{sufijo}", nombre="Ruta 1"),
        Ruta(codigo=f"R2-{sufijo}", nombre="Ruta 2"),
    ]
    db.add_all(rutas)
    db.flush()
    admin = crear_usuario(db, "admin-fase8")
    admin.roles = [db.scalar(select(Rol).where(Rol.nombre == "Admin"))]
    db.commit()
    return SimpleNamespace(
        db=db,
        client=cliente,
        rutas=rutas,
        admin=admin,
        h=encabezados(admin, "usuarios:gestionar", roles=("Admin",)),
    )


def _nuevo(email: str | None = None, **extra):
    return {
        "email": email or f"nuevo-{uuid.uuid4().hex[:8]}@ds.gt",
        "nombre_completo": "Vendedor Nuevo",
        "password": "ClaveSegura123",
        "roles": ["Ventas"],
        **extra,
    }


def _usuarios(e, **params) -> list[dict]:
    return e.client.get(BASE, params={"limit": 200, **params}, headers=e.h).json()["usuarios"]


def test_exige_permiso_y_autenticacion(entorno):
    e = entorno
    assert e.client.get(BASE).status_code == 401
    ventas = crear_usuario(e.db, "ventas")
    sin_permiso = encabezados(ventas, "carga_ruta:generar", roles=("Ventas",))
    assert e.client.get(BASE, headers=sin_permiso).status_code == 403
    assert e.client.post(BASE, json=_nuevo(), headers=sin_permiso).status_code == 403


def test_crear_usuario_con_rol_y_rutas_y_puede_iniciar_sesion(entorno):
    e = entorno
    r = e.client.post(BASE, json=_nuevo(ruta_ids=[str(e.rutas[0].id)]), headers=e.h)
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["roles"] == ["Ventas"] and u["activo"] is True
    assert [x["id"] for x in u["rutas"]] == [str(e.rutas[0].id)]
    assert "password" not in u and "password_hash" not in u

    login = e.client.post(LOGIN, json={"email": u["email"], "password": "ClaveSegura123"})
    assert login.status_code == 200 and login.json()["usuario"]["roles"] == ["Ventas"]


def test_validaciones_de_alta(entorno):
    e = entorno
    assert e.client.post(BASE, json=_nuevo("dup@ds.gt"), headers=e.h).status_code == 201
    dup = e.client.post(BASE, json=_nuevo("DUP@ds.gt"), headers=e.h)
    assert dup.status_code == 409 and dup.json()["codigo"] == "EMAIL_DUPLICADO"

    rol = e.client.post(BASE, json=_nuevo(roles=["Inexistente"]), headers=e.h)
    assert rol.status_code == 400 and rol.json()["codigo"] == "ROL_INVALIDO"

    ruta = e.client.post(BASE, json=_nuevo(ruta_ids=[str(uuid.uuid4())]), headers=e.h)
    assert ruta.status_code == 400 and ruta.json()["codigo"] == "RUTA_INVALIDA"

    prov = e.client.post(BASE, json=_nuevo(roles=["Proveedor"]), headers=e.h)
    assert prov.status_code == 400 and prov.json()["codigo"] == "PROVEEDOR_REQUERIDO"

    assert e.client.post(BASE, json=_nuevo(password="corta"), headers=e.h).status_code == 422


def test_reasignar_rutas_una_ruta_un_vendedor(entorno):
    e = entorno
    primero = e.client.post(BASE, json=_nuevo(ruta_ids=[str(e.rutas[0].id)]), headers=e.h).json()
    segundo = e.client.post(BASE, json=_nuevo(), headers=e.h).json()

    r = e.client.patch(
        f"{BASE}/{segundo['id']}",
        json={"ruta_ids": [str(e.rutas[0].id), str(e.rutas[1].id)], "nombre_completo": "Otro"},
        headers=e.h,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["rutas"]) == 2 and r.json()["nombre_completo"] == "Otro"
    viejo = next(u for u in _usuarios(e) if u["id"] == primero["id"])
    assert viejo["rutas"] == []

    libre = e.client.patch(f"{BASE}/{segundo['id']}", json={"ruta_ids": []}, headers=e.h)
    assert libre.json()["rutas"] == []
    assert e.client.patch(f"{BASE}/{uuid.uuid4()}", json={}, headers=e.h).status_code == 404


def test_cambiar_clave_y_rol(entorno):
    e = entorno
    u = e.client.post(BASE, json=_nuevo(), headers=e.h).json()
    r = e.client.patch(
        f"{BASE}/{u['id']}", json={"password": "OtraClave12345", "roles": ["Admin"]}, headers=e.h
    )
    assert r.status_code == 200 and r.json()["roles"] == ["Admin"]
    viejo = e.client.post(LOGIN, json={"email": u["email"], "password": "ClaveSegura123"})
    nuevo = e.client.post(LOGIN, json={"email": u["email"], "password": "OtraClave12345"})
    assert viejo.status_code == 401 and nuevo.status_code == 200


def test_desactivar_impide_login_y_reactivar_lo_permite(entorno):
    e = entorno
    u = e.client.post(BASE, json=_nuevo(), headers=e.h).json()
    creds = {"email": u["email"], "password": "ClaveSegura123"}

    off = e.client.patch(f"{BASE}/{u['id']}/status", json={"activo": False}, headers=e.h)
    assert off.status_code == 200 and off.json()["activo"] is False
    assert e.client.post(LOGIN, json=creds).status_code == 401
    assert len(_usuarios(e, activo=False, q=u["email"])) == 1

    e.client.patch(f"{BASE}/{u['id']}/status", json={"activo": True}, headers=e.h)
    assert e.client.post(LOGIN, json=creds).status_code == 200


def test_protege_al_administrador(entorno):
    e = entorno
    propio = e.client.patch(f"{BASE}/{e.admin.id}/status", json={"activo": False}, headers=e.h)
    assert propio.status_code == 409
    assert propio.json()["codigo"] == "AUTOMODIFICACION_NO_PERMITIDA"

    # Deja a `segundo` como único admin activo distinto del actor y luego desactiva al actor.
    segundo = e.client.post(BASE, json=_nuevo(roles=["Admin"]), headers=e.h).json()
    conservados = [e.admin.id, uuid.UUID(segundo["id"])]
    e.db.execute(update(Usuario).where(Usuario.id.not_in(conservados)).values(activo=False))
    e.db.execute(update(Usuario).where(Usuario.id == e.admin.id).values(activo=False))
    e.db.commit()

    ultimo = e.client.patch(f"{BASE}/{segundo['id']}/status", json={"activo": False}, headers=e.h)
    assert ultimo.status_code == 409 and ultimo.json()["codigo"] == "ULTIMO_ADMIN"
    quitar = e.client.patch(f"{BASE}/{segundo['id']}", json={"roles": ["Ventas"]}, headers=e.h)
    assert quitar.status_code == 409 and quitar.json()["codigo"] == "ULTIMO_ADMIN"


def test_listar_roles_y_filtros(entorno):
    e = entorno
    e.client.post(BASE, json=_nuevo("filtro-uno@ds.gt"), headers=e.h)
    roles = e.client.get(f"{BASE}/roles", headers=e.h).json()
    assert {"Admin", "Ventas"} <= {r["nombre"] for r in roles}

    por_rol = _usuarios(e, rol="Ventas", q="filtro-uno")
    assert len(por_rol) == 1 and por_rol[0]["email"] == "filtro-uno@ds.gt"
    assert _usuarios(e, rol="Admin", q="filtro-uno") == []
