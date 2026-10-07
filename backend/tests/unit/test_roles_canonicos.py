"""M01: nombres canónicos de rol, matriz rol→permiso intacta y rol Liquidador acotado."""

import pytest

from app.api.deps import require_permission
from app.core.errors import AppError
from app.db.seeds.seed_rbac import MATRIZ_ROL_PERMISO, PERMISOS, ROLES
from app.domain.enums import NombreRol
from app.schemas.auth import UsuarioAutenticado

# Matriz vigente ANTES del renombrado (con los nombres anteriores como clave).
MATRIZ_ANTERIOR: dict[str, set[str]] = {
    "Admin": set(PERMISOS),
    "Inventario": {
        "etl:cargar",
        "prediccion:consultar",
        "inventario:leer",
        "inventario:ajustar",
        "productos:crear",
        "productos:editar",
        "productos:eliminar",
        "alertas:leer",
    },
    "Ventas": {
        "etl:cargar",
        "prediccion:consultar",
        "carga_ruta:generar",
        "carga_ruta:aprobar",
        "inventario:leer",
        "alertas:leer",
    },
    "Bodega": {"carga_ruta:despachar", "inventario:leer", "inventario:ajustar", "alertas:leer"},
    "Compras": {
        "prediccion:consultar",
        "inventario:leer",
        "pedido_proveedor:gestionar",
        "alertas:leer",
    },
    "Gerente": {
        "reportes:leer",
        "prediccion:consultar",
        "carga_ruta:aprobar",
        "inventario:leer",
        "ml:metricas:leer",
        "ml:reentrenar",
        "alertas:leer",
        "liquidaciones:leer",
    },
    "Proveedor": {"pedido_proveedor:confirmar"},
    "Liquidador": {"liquidaciones:registrar", "liquidaciones:cerrar", "liquidaciones:leer"},
}
# M02 (ADR-18): únicos permisos añadidos a la matriz tras el renombrado. Ningún otro rol cambia.
ALTAS_M02: dict[str, set[str]] = {
    "Admin": {"catalogos:leer", "catalogos:gestionar"},
    "Inventario": {"catalogos:leer"},
    "Gerente": {"catalogos:leer"},
}
RENOMBRE = {
    "Admin": NombreRol.ADMINISTRADOR,
    "Inventario": NombreRol.ENCARGADO_INVENTARIO,
    "Ventas": NombreRol.ENCARGADO_VENTAS,
    "Bodega": NombreRol.ENCARGADO_BODEGA,
    "Compras": NombreRol.ENCARGADO_COMPRAS,
    "Gerente": NombreRol.GERENTE,
    "Proveedor": NombreRol.PROVEEDOR,
    "Liquidador": NombreRol.LIQUIDADOR,
}


def test_los_roles_sembrados_son_exactamente_los_canonicos():
    assert set(ROLES) == {r.value for r in NombreRol}
    assert set(MATRIZ_ROL_PERMISO) == set(ROLES)
    assert not {"Admin", "Inventario", "Ventas", "Bodega", "Compras"} & set(ROLES)


@pytest.mark.parametrize("anterior", list(MATRIZ_ANTERIOR))
def test_cada_rol_conserva_los_mismos_permisos_tras_el_renombrado(anterior):
    esperado = MATRIZ_ANTERIOR[anterior] | ALTAS_M02.get(anterior, set())
    assert set(MATRIZ_ROL_PERMISO[RENOMBRE[anterior]]) == esperado


def test_liquidador_tiene_exactamente_tres_permisos():
    permisos = MATRIZ_ROL_PERMISO[NombreRol.LIQUIDADOR]
    assert len(permisos) == 3
    assert set(permisos) == {
        "liquidaciones:registrar",
        "liquidaciones:cerrar",
        "liquidaciones:leer",
    }
    assert "liquidaciones:corregir" not in permisos
    assert "responsable de registrar y cerrar" in ROLES[NombreRol.LIQUIDADOR].lower()


@pytest.mark.parametrize(
    "permiso_requerido",
    [
        "carga_ruta:generar",  # cargas
        "carga_ruta:aprobar",
        "carga_ruta:despachar",
        "pedido_proveedor:gestionar",  # compras
        "pedido_proveedor:confirmar",
        "usuarios:gestionar",  # administración de usuarios
        "liquidaciones:corregir",
    ],
)
def test_liquidador_recibe_403_fuera_de_su_alcance(permiso_requerido):
    usuario = UsuarioAutenticado(
        id="11111111-1111-1111-1111-111111111111",
        roles=[NombreRol.LIQUIDADOR],
        permisos=list(MATRIZ_ROL_PERMISO[NombreRol.LIQUIDADOR]),
    )
    with pytest.raises(AppError) as exc_info:
        require_permission(permiso_requerido)(usuario)
    assert exc_info.value.status_code == 403
