"""M02 contra PostgreSQL real: CHECKs y únicos parciales, equipos de ruta, rutas, empleados,
productos con paquete y permisos sembrados (`catalogos:leer|gestionar`)."""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.seeds.seed_rbac import MATRIZ_ROL_PERMISO, seed_roles_y_permisos
from app.domain.models.auth import Rol
from app.domain.models.catalog import (
    Categoria,
    Empleado,
    EquipoRuta,
    Producto,
    ProductoAliasExcel,
    Ruta,
)
from app.repositories import ruta_repo

from .conftest import crear_usuario, encabezados

CAT = "/api/v1/catalog"
EMP = "/api/v1/employees"
PROD = "/api/v1/products"
HOY = date.today()


def _sufijo() -> str:
    return uuid.uuid4().hex[:6].upper()


@pytest.fixture
def e(db_tx, cliente):
    db = db_tx
    admin = crear_usuario(db, "admin-m02")
    ruta = Ruta(codigo=f"R-{_sufijo()}", nombre="Ruta de prueba")
    otra = Ruta(codigo=f"R-{_sufijo()}", nombre="Otra ruta")
    db.add_all([ruta, otra])
    empleados = [Empleado(nombre_completo=n) for n in ("Ana", "Beto", "Carla", "Dario")]
    db.add_all(empleados)
    db.commit()
    return SimpleNamespace(
        db=db,
        client=cliente,
        ruta=ruta,
        otra=otra,
        emp=empleados,
        admin=admin,
        h=encabezados(admin, "catalogos:leer", "catalogos:gestionar"),
        hl=encabezados(admin, "catalogos:leer"),
    )


def _integrante(empleado, rol, pct):
    return {"empleado_id": str(empleado.id), "rol_en_ruta": rol, "porcentaje_reparto": pct}


def _guardar_equipo(e, ruta, integrantes, **extra):
    return e.client.put(
        f"{CAT}/routes/{ruta.id}/team", json={"integrantes": integrantes, **extra}, headers=e.h
    )


def _equipo_valido(e):
    ana, beto, carla = e.emp[:3]
    return [
        _integrante(ana, "vendedor", "35"),
        _integrante(beto, "chofer", "33"),
        _integrante(carla, "auxiliar", "32"),
    ]


# ------------------------------------------------------------------ CHECKs y únicos parciales
def _fila(e, **campos):
    base = dict(
        ruta_id=e.ruta.id,
        empleado_id=e.emp[0].id,
        rol_en_ruta="vendedor",
        porcentaje_reparto=100,
        vigente_desde=HOY,
    )
    return EquipoRuta(**{**base, **campos})


def _debe_fallar(db, *filas):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add_all(filas)
            db.flush()


@pytest.mark.parametrize(
    "campos",
    [
        {"porcentaje_reparto": 100.01},
        {"porcentaje_reparto": -1},
        {"rol_en_ruta": "gerente"},
        {"vigente_hasta": HOY - timedelta(days=1)},  # hasta < desde
    ],
)
def test_checks_de_equipo_ruta(e, campos):
    _debe_fallar(e.db, _fila(e, **campos))


def test_vigencia_de_un_solo_dia_es_valida(e):
    e.db.add(_fila(e, vigente_hasta=HOY))
    e.db.flush()


def test_un_solo_vendedor_vigente_por_ruta(e):
    e.db.add(_fila(e, empleado_id=e.emp[0].id, porcentaje_reparto=50))
    e.db.flush()
    _debe_fallar(e.db, _fila(e, empleado_id=e.emp[1].id, porcentaje_reparto=50))


def test_vendedor_cerrado_no_bloquea_a_uno_nuevo(e):
    e.db.add(_fila(e, empleado_id=e.emp[0].id, vigente_hasta=HOY - timedelta(days=0)))
    e.db.add(_fila(e, empleado_id=e.emp[1].id))
    e.db.flush()


def test_empleado_no_se_repite_en_la_misma_ruta_con_vigencia_abierta(e):
    e.db.add(_fila(e, rol_en_ruta="chofer", porcentaje_reparto=50))
    e.db.flush()
    _debe_fallar(e.db, _fila(e, rol_en_ruta="auxiliar", porcentaje_reparto=50))


def test_mismo_empleado_puede_estar_en_otra_ruta(e):
    e.db.add(_fila(e, rol_en_ruta="chofer"))
    e.db.add(_fila(e, ruta_id=e.otra.id, rol_en_ruta="chofer"))
    e.db.flush()


def test_usuario_unico_por_empleado(e):
    u = crear_usuario(e.db, "usuario-vinculado")
    e.emp[0].usuario_id = u.id
    e.db.flush()
    _debe_fallar_empleado = Empleado(nombre_completo="Duplicado", usuario_id=u.id)
    with pytest.raises(IntegrityError):
        with e.db.begin_nested():
            e.db.add(_debe_fallar_empleado)
            e.db.flush()


@pytest.mark.parametrize("campos", [{"unidades_por_paquete": 0}, {"medida_ml": 0}])
def test_checks_de_producto_paquete(e, campos):
    cat = Categoria(nombre=f"Cat-{_sufijo()}")
    e.db.add(cat)
    e.db.flush()
    with pytest.raises(IntegrityError):
        with e.db.begin_nested():
            e.db.add(Producto(sku=f"P{_sufijo()}", nombre="x", categoria_id=cat.id, **campos))
            e.db.flush()


def test_alias_unico_y_con_restrict_sobre_producto(e):
    cat = Categoria(nombre=f"Cat-{_sufijo()}")
    e.db.add(cat)
    e.db.flush()
    p1 = Producto(sku=f"P{_sufijo()}", nombre="x", categoria_id=cat.id)
    p2 = Producto(sku=f"P{_sufijo()}", nombre="y", categoria_id=cat.id)
    e.db.add_all([p1, p2])
    e.db.flush()
    e.db.add(ProductoAliasExcel(producto_id=p1.id, alias="3030-COLA"))
    e.db.flush()
    with pytest.raises(IntegrityError):
        with e.db.begin_nested():
            e.db.add(ProductoAliasExcel(producto_id=p2.id, alias="3030-COLA"))
            e.db.flush()


# ------------------------------------------------------------------ equipo: reglas del servicio
def test_equipo_que_suma_100_se_guarda(e):
    r = _guardar_equipo(e, e.ruta, _equipo_valido(e))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["suma_100"] is True and cuerpo["tiene_vendedor"] is True
    assert cuerpo["suma_porcentaje"] == "100.00" and len(cuerpo["integrantes"]) == 3


@pytest.mark.parametrize("porcentajes", [("35", "33", "31.99"), ("40", "40", "30")])
def test_equipo_que_no_suma_100_se_rechaza_y_no_guarda_nada(e, porcentajes):
    ana, beto, carla = e.emp[:3]
    integrantes = [
        _integrante(ana, "vendedor", porcentajes[0]),
        _integrante(beto, "chofer", porcentajes[1]),
        _integrante(carla, "auxiliar", porcentajes[2]),
    ]
    r = _guardar_equipo(e, e.ruta, integrantes)
    assert r.status_code == 400 and r.json()["codigo"] == "EQUIPO_NO_SUMA_100"
    assert e.db.scalar(select(func.count()).select_from(EquipoRuta)) == 0


def test_reemplazo_cierra_las_vigencias_anteriores_sin_borrarlas(e):
    ana, beto, carla, dario = e.emp
    assert _guardar_equipo(
        e, e.ruta, _equipo_valido(e), vigente_desde=str(HOY - timedelta(days=30))
    )
    nuevo = [_integrante(dario, "vendedor", "60"), _integrante(ana, "chofer", "40")]
    r = _guardar_equipo(e, e.ruta, nuevo, vigente_desde=str(HOY))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert {i["nombre_completo"] for i in cuerpo["integrantes"]} == {"Dario", "Ana"}
    assert len(cuerpo["historial"]) == 3  # el equipo anterior sigue, con vigencia cerrada
    assert {h["vigente_hasta"] for h in cuerpo["historial"]} == {str(HOY - timedelta(days=1))}
    assert e.db.scalar(select(func.count()).select_from(EquipoRuta)) == 5  # nada se borra


def test_get_equipo_devuelve_vigente_e_historial(e):
    _guardar_equipo(e, e.ruta, _equipo_valido(e), vigente_desde=str(HOY - timedelta(days=10)))
    r = e.client.get(f"{CAT}/routes/{e.ruta.id}/team", headers=e.hl)
    assert (
        r.status_code == 200 and len(r.json()["integrantes"]) == 3 and r.json()["historial"] == []
    )


def test_reemplazo_el_mismo_dia_conserva_la_restriccion_de_vigencia(e):
    assert _guardar_equipo(e, e.ruta, _equipo_valido(e)).status_code == 200
    r = _guardar_equipo(e, e.ruta, [_integrante(e.emp[0], "vendedor", "100")])
    assert r.status_code == 200, (
        r.text
    )  # corrección el mismo día: la vigencia anterior no se invierte
    assert len(r.json()["integrantes"]) == 1


def test_vigencia_anterior_al_equipo_vigente_se_rechaza(e):
    _guardar_equipo(e, e.ruta, _equipo_valido(e))
    r = _guardar_equipo(
        e,
        e.ruta,
        [_integrante(e.emp[0], "vendedor", "100")],
        vigente_desde=str(HOY - timedelta(days=5)),
    )
    assert r.status_code == 400 and r.json()["codigo"] == "VIGENCIA_INVALIDA"


def test_empleado_repetido_o_dos_vendedores_se_rechazan(e):
    ana, beto = e.emp[:2]
    r = _guardar_equipo(
        e, e.ruta, [_integrante(ana, "vendedor", "50"), _integrante(ana, "chofer", "50")]
    )
    assert r.json()["codigo"] == "EMPLEADO_REPETIDO"
    r = _guardar_equipo(
        e, e.ruta, [_integrante(ana, "vendedor", "50"), _integrante(beto, "vendedor", "50")]
    )
    assert r.json()["codigo"] == "VENDEDOR_MULTIPLE"


def test_equipo_sin_vendedor_se_permite_pero_se_reporta(e):
    ana, beto = e.emp[:2]
    r = _guardar_equipo(
        e, e.ruta, [_integrante(ana, "chofer", "50"), _integrante(beto, "auxiliar", "50")]
    )
    assert r.status_code == 200 and r.json()["tiene_vendedor"] is False
    informe = {
        x["ruta_id"]: x for x in e.client.get(f"{CAT}/teams/incomplete", headers=e.hl).json()
    }
    assert informe[str(e.ruta.id)]["motivos"] == ["sin_vendedor"]


def test_empleado_inexistente_o_de_baja_se_rechaza(e):
    r = _guardar_equipo(
        e,
        e.ruta,
        [
            {
                "empleado_id": str(uuid.uuid4()),
                "rol_en_ruta": "vendedor",
                "porcentaje_reparto": "100",
            }
        ],
    )
    assert r.status_code == 404 and r.json()["codigo"] == "EMPLEADO_NO_ENCONTRADO"
    e.emp[0].activo = False
    e.db.commit()
    r = _guardar_equipo(e, e.ruta, [_integrante(e.emp[0], "vendedor", "100")])
    assert r.status_code == 409 and r.json()["codigo"] == "EMPLEADO_INACTIVO"


def test_ruta_inactiva_no_admite_equipo(e):
    e.ruta.activa = False
    e.db.commit()
    r = _guardar_equipo(e, e.ruta, [_integrante(e.emp[0], "vendedor", "100")])
    assert r.status_code == 409 and r.json()["codigo"] == "RUTA_INACTIVA"


def test_rutas_sin_equipo_o_incompletas_aparecen_en_el_informe(e):
    _guardar_equipo(e, e.ruta, _equipo_valido(e))  # e.ruta queda completa
    informe = e.client.get(f"{CAT}/teams/incomplete", headers=e.hl).json()
    ids = {x["ruta_id"]: x["motivos"] for x in informe}
    assert str(e.ruta.id) not in ids
    assert ids[str(e.otra.id)] == ["sin_equipo"]


def test_equipo_con_suma_distinta_de_100_ya_guardada_se_detecta(e):
    # Datos heredados o cargados por otra vía: el informe es la red de seguridad.
    e.db.add(_fila(e, porcentaje_reparto=60))
    e.db.commit()
    informe = {
        x["ruta_id"]: x for x in e.client.get(f"{CAT}/teams/incomplete", headers=e.hl).json()
    }
    assert informe[str(e.ruta.id)]["motivos"] == ["suma_distinta_de_100"]
    assert informe[str(e.ruta.id)]["suma_porcentaje"] == "60.00"


# ------------------------------------------------------------------ vendedor: dos fuentes de verdad
def test_vendedor_incoherente_se_rechaza_en_equipo_y_en_ruta(e):
    u_ruta, u_emp = crear_usuario(e.db, "vend-ruta"), crear_usuario(e.db, "vend-emp")
    e.ruta.vendedor_id = u_ruta.id
    e.emp[0].usuario_id = u_emp.id
    e.db.commit()
    r = _guardar_equipo(e, e.ruta, [_integrante(e.emp[0], "vendedor", "100")])
    assert r.status_code == 409 and r.json()["codigo"] == "VENDEDOR_INCOHERENTE"

    # Alinear ambos permite guardar; luego cambiar la ruta a otro usuario también se bloquea.
    e.ruta.vendedor_id = u_emp.id
    e.db.commit()
    assert _guardar_equipo(e, e.ruta, [_integrante(e.emp[0], "vendedor", "100")]).status_code == 200
    r = e.client.patch(
        f"{CAT}/routes/{e.ruta.id}", json={"vendedor_id": str(u_ruta.id)}, headers=e.h
    )
    assert r.status_code == 409 and r.json()["codigo"] == "VENDEDOR_INCOHERENTE"


def test_informe_de_rutas_desalineadas_no_sincroniza_nada(e):
    u_ruta, u_emp = crear_usuario(e.db, "v-ruta"), crear_usuario(e.db, "v-emp")
    e.ruta.vendedor_id = u_ruta.id
    e.db.commit()
    _guardar_equipo(e, e.ruta, [_integrante(e.emp[0], "vendedor", "100")])  # empleado sin usuario
    informe = e.client.get(f"{CAT}/teams/misaligned", headers=e.hl).json()
    fila = next(x for x in informe if x["ruta_id"] == str(e.ruta.id))
    assert fila["vendedor_id_ruta"] == str(u_ruta.id) and fila["usuario_id_empleado"] is None
    e.db.refresh(e.ruta)
    assert e.ruta.vendedor_id == u_ruta.id  # `rutas.vendedor_id` intacto
    assert u_emp.id  # (usuario libre: no se vincula solo)


# ------------------------------------------------------------------ rutas
def test_crear_ruta_guarda_el_codigo_en_mayusculas_y_rechaza_duplicados(e):
    codigo = f"nueva-{_sufijo().lower()}"
    r = e.client.post(f"{CAT}/routes", json={"codigo": codigo, "nombre": "Nueva"}, headers=e.h)
    assert r.status_code == 201 and r.json()["codigo"] == codigo.upper()
    r = e.client.post(
        f"{CAT}/routes", json={"codigo": codigo.upper(), "nombre": "Otra"}, headers=e.h
    )
    assert r.status_code == 409 and r.json()["codigo"] == "RUTA_DUPLICADA"


def test_el_codigo_de_la_ruta_no_se_modifica(e):
    r = e.client.patch(
        f"{CAT}/routes/{e.ruta.id}", json={"codigo": "OTRO", "nombre": "Renombrada"}, headers=e.h
    )
    assert r.status_code == 200 and r.json()["nombre"] == "Renombrada"
    assert r.json()["codigo"] == e.ruta.codigo


def test_desactivar_y_reactivar_ruta_es_idempotente_y_conserva_la_fila(e):
    for _ in range(2):
        r = e.client.post(f"{CAT}/routes/{e.ruta.id}/deactivate", headers=e.h)
        assert r.status_code == 200 and r.json()["activa"] is False
    activas = {x["id"] for x in e.client.get(f"{CAT}/routes", headers=e.hl).json()}
    assert str(e.ruta.id) not in activas  # el filtro público sigue mostrando solo activas
    todas = {x["id"] for x in e.client.get(f"{CAT}/routes/admin", headers=e.hl).json()}
    assert str(e.ruta.id) in todas
    assert e.client.post(f"{CAT}/routes/{e.ruta.id}/activate", headers=e.h).json()["activa"] is True


def test_desactivar_con_liquidaciones_en_borrador_se_bloquea(e, monkeypatch):
    borrador = uuid.uuid4()
    monkeypatch.setattr(ruta_repo, "liquidaciones_en_borrador", lambda db, rid: [borrador])
    r = e.client.post(f"{CAT}/routes/{e.ruta.id}/deactivate", headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "RUTA_CON_LIQUIDACIONES"
    assert e.db.get(Ruta, e.ruta.id).activa is True


def test_ruta_inexistente_responde_404(e):
    r = e.client.get(f"{CAT}/routes/{uuid.uuid4()}", headers=e.hl)
    assert r.status_code == 404 and r.json()["codigo"] == "RUTA_NO_ENCONTRADA"


# ------------------------------------------------------------------ empleados
def test_crud_de_empleados_con_baja_logica(e):
    r = e.client.post(EMP, json={"nombre_completo": "  Elena Soto "}, headers=e.h)
    assert r.status_code == 201 and r.json()["nombre_completo"] == "Elena Soto"
    eid = r.json()["id"]
    assert (
        e.client.patch(
            f"{EMP}/{eid}", json={"nombre_completo": "Elena S."}, headers=e.h
        ).status_code
        == 200
    )
    assert e.client.delete(f"{EMP}/{eid}", headers=e.h).status_code == 204
    assert e.client.delete(f"{EMP}/{eid}", headers=e.h).status_code == 204  # idempotente
    assert e.db.get(Empleado, uuid.UUID(eid)).activo is False  # sigue en la BD
    activos = {x["id"] for x in e.client.get(EMP, headers=e.hl).json()["items"]}
    assert eid not in activos
    inactivos = e.client.get(EMP, params={"activo": False}, headers=e.hl).json()["items"]
    assert eid in {x["id"] for x in inactivos}
    assert e.client.post(f"{EMP}/{eid}/reactivate", headers=e.h).json()["activo"] is True


def test_empleado_en_equipo_vigente_no_se_da_de_baja(e):
    _guardar_equipo(e, e.ruta, _equipo_valido(e))
    r = e.client.delete(f"{EMP}/{e.emp[0].id}", headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "EMPLEADO_EN_USO"
    assert e.db.get(Empleado, e.emp[0].id).activo is True


def test_empleado_fuera_del_equipo_vigente_si_se_da_de_baja(e):
    _guardar_equipo(e, e.ruta, _equipo_valido(e), vigente_desde=str(HOY - timedelta(days=3)))
    _guardar_equipo(e, e.ruta, [_integrante(e.emp[3], "vendedor", "100")])  # Ana, Beto, Carla salen
    assert e.client.delete(f"{EMP}/{e.emp[0].id}", headers=e.h).status_code == 204


def test_vincular_usuario_a_dos_empleados_se_rechaza(e):
    u = crear_usuario(e.db, "usuario-unico")
    e.db.commit()
    ok = e.client.post(EMP, json={"nombre_completo": "Uno", "usuario_id": str(u.id)}, headers=e.h)
    assert ok.status_code == 201
    r = e.client.post(EMP, json={"nombre_completo": "Dos", "usuario_id": str(u.id)}, headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "USUARIO_YA_VINCULADO"
    r = e.client.post(
        EMP, json={"nombre_completo": "Tres", "usuario_id": str(uuid.uuid4())}, headers=e.h
    )
    assert r.status_code == 404 and r.json()["codigo"] == "USUARIO_NO_ENCONTRADO"


def test_solo_lectura_no_puede_escribir(e):
    assert e.client.post(EMP, json={"nombre_completo": "Zeta"}, headers=e.hl).status_code == 403
    assert (
        e.client.put(
            f"{CAT}/routes/{e.ruta.id}/team", json={"integrantes": []}, headers=e.hl
        ).status_code
        == 403
    )


# ------------------------------------------------------------------ productos con paquete
def test_producto_acepta_y_devuelve_los_campos_de_paquete(e):
    cat = Categoria(nombre=f"Cat-{_sufijo()}")
    e.db.add(cat)
    e.db.commit()
    h = encabezados(e.admin, "productos:crear", "productos:editar", "inventario:leer")
    cuerpo = {
        "sku": f"{_sufijo()}",
        "nombre": "BIG COLA",
        "categoria_id": str(cat.id),
        "unidad_medida": "paquete",
        "unidades_por_paquete": 6,
        "medida_ml": 3030,
        "sabor": "  COLA ",
    }
    r = e.client.post(PROD, json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["unidades_por_paquete"], p["medida_ml"], p["sabor"]) == (6, 3030, "COLA")
    r = e.client.patch(
        f"{PROD}/{p['id']}", json={"medida_ml": None, "unidades_por_paquete": 12}, headers=h
    )
    assert (
        r.status_code == 200
        and r.json()["medida_ml"] is None
        and r.json()["unidades_por_paquete"] == 12
    )


def test_producto_sin_los_campos_nuevos_conserva_los_valores_por_defecto(e):
    cat = Categoria(nombre=f"Cat-{_sufijo()}")
    e.db.add(cat)
    e.db.commit()
    h = encabezados(e.admin, "productos:crear")
    r = e.client.post(
        PROD,
        json={"sku": _sufijo(), "nombre": "Compatible", "categoria_id": str(cat.id)},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["unidades_por_paquete"] == 1 and r.json()["medida_ml"] is None
    assert r.json()["unidad_medida"] == "unidad"


# ------------------------------------------------------------------ permisos sembrados
def test_el_seed_otorga_los_permisos_nuevos_sin_quitar_los_existentes(e):
    antes = {r.nombre: {p.codigo for p in r.permisos} for r in e.db.scalars(select(Rol)).all()}
    for _ in range(2):  # idempotente
        seed_roles_y_permisos(e.db)
    e.db.flush()
    for nombre in ("Administrador", "Gerente", "EncargadoInventario"):
        rol = e.db.scalar(select(Rol).where(Rol.nombre == nombre))
        codigos = {p.codigo for p in rol.permisos}
        assert set(MATRIZ_ROL_PERMISO[nombre]) <= codigos
        assert antes.get(nombre, set()) <= codigos  # los usuarios existentes conservan acceso
    admin = e.db.scalar(select(Rol).where(Rol.nombre == "Administrador"))
    assert {"catalogos:leer", "catalogos:gestionar"} <= {p.codigo for p in admin.permisos}
    bodega = e.db.scalar(select(Rol).where(Rol.nombre == "EncargadoBodega"))
    assert not {"catalogos:leer", "catalogos:gestionar"} & {p.codigo for p in bodega.permisos}
