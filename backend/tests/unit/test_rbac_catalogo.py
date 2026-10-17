"""ADR-19: el catálogo sembrado es coherente con el código que lo usa (sin BD)."""

import re
from pathlib import Path

from app.db.seeds.seed_rbac import MATRIZ_ROL_PERMISO, PANTALLAS, PERMISOS, ROLES, ROLES_ACTIVOS
from app.domain.enums import NombreRol

API = Path(__file__).resolve().parents[2] / "app" / "api"
PATRON = re.compile(r'require_permission\(\s*"([^"]+)"\s*\)')


def test_todo_permiso_exigido_por_la_api_existe_en_el_catalogo():
    usados = {
        codigo
        for archivo in API.rglob("*.py")
        for codigo in PATRON.findall(archivo.read_text("utf-8"))
    }
    assert usados, "no se detectó ningún guarda: ¿cambió el patrón?"
    assert usados <= set(PERMISOS), f"permisos sin sembrar: {sorted(usados - set(PERMISOS))}"


def test_toda_pantalla_se_habilita_con_permisos_del_catalogo():
    claves = [p[0] for p in PANTALLAS]
    assert len(claves) == len(set(claves))
    for clave, _, ruta, _, _, _, permisos in PANTALLAS:
        assert ruta.startswith("/"), clave
        assert permisos and set(permisos) <= set(PERMISOS), clave


def test_el_administrador_tiene_todo_y_hay_tres_roles_activos():
    assert set(MATRIZ_ROL_PERMISO[NombreRol.ADMINISTRADOR]) == set(PERMISOS)
    assert ROLES_ACTIVOS == {
        NombreRol.ADMINISTRADOR,
        NombreRol.GERENTE,
        NombreRol.LIQUIDADOR,
    }
    assert ROLES_ACTIVOS <= set(ROLES)


def test_el_liquidador_no_corrige_ni_gestiona():
    permisos = set(MATRIZ_ROL_PERMISO[NombreRol.LIQUIDADOR])
    assert not {"liquidaciones:corregir", "usuarios:gestionar", "roles:gestionar"} & permisos
