"""Seeds iniciales: roles, permisos (matriz 1.4), usuario admin y `parametros_sistema`.

Idempotente: puede ejecutarse varias veces sin duplicar filas ni pisar el hash de
contraseña del admin si ya existe.

Uso (desde `backend/`, con el venv activo):
    python -m app.db.seeds.seed_rbac
"""

from sqlalchemy.orm import Session

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.domain.models.auth import Permiso, Rol, Usuario
from app.domain.models.ml import ParametroSistema

ROLES: dict[str, str] = {
    "Admin": "Acceso total al sistema.",
    "Inventario": "Carga de histórico y gestión de existencias.",
    "Ventas": "Generación y aprobación de cargas de ruta.",
    "Bodega": "Despacho de cargas y ajuste de inventario.",
    "Compras": "Gestión de pedidos a proveedores.",
    "Gerente": "Aprobación de cargas y monitoreo de modelos ML.",
    "Proveedor": "Confirmación de pedidos propios (acceso restringido por proveedor_id).",
}

PERMISOS: dict[str, str] = {
    "usuarios:gestionar": "Alta, baja y edición de usuarios y roles.",
    "etl:cargar": "Ingesta de histórico de ventas desde Excel.",
    "prediccion:consultar": "Consulta de pronósticos de demanda.",
    "carga_ruta:generar": "Generación de planes de carga de ruta.",
    "carga_ruta:aprobar": "Aprobación o rechazo de planes de carga.",
    "carga_ruta:despachar": "Confirmación de despacho (kardex de salida).",
    "inventario:leer": "Consulta de existencias.",
    "inventario:ajustar": "Ajustes manuales de existencias.",
    "pedido_proveedor:gestionar": "Creación y edición de pedidos a proveedores.",
    "pedido_proveedor:confirmar": "Confirmación de pedidos por el proveedor.",
    "ml:metricas:leer": "Consulta de métricas y degradación de modelos.",
    "ml:reentrenar": "Solicitud de reentrenamiento de modelos.",
    "alertas:leer": "Consulta de alertas del sistema.",
    "reportes:leer": "Reportes gerenciales: rotación, quiebres, comisiones y exportación.",
}

# Matriz 1.4 de la especificación (columna Worker se excluye: no es un rol de login).
MATRIZ_ROL_PERMISO: dict[str, tuple[str, ...]] = {
    "Admin": tuple(PERMISOS),
    "Inventario": (
        "etl:cargar",
        "prediccion:consultar",
        "inventario:leer",
        "inventario:ajustar",
        "alertas:leer",
    ),
    "Ventas": (
        "etl:cargar",
        "prediccion:consultar",
        "carga_ruta:generar",
        "carga_ruta:aprobar",
        "inventario:leer",
        "alertas:leer",
    ),
    "Bodega": (
        "carga_ruta:despachar",
        "inventario:leer",
        "inventario:ajustar",
        "alertas:leer",
    ),
    "Compras": (
        "prediccion:consultar",
        "inventario:leer",
        "pedido_proveedor:gestionar",
        "alertas:leer",
    ),
    "Gerente": (
        "reportes:leer",
        "prediccion:consultar",
        "carga_ruta:aprobar",
        "inventario:leer",
        "ml:metricas:leer",
        "ml:reentrenar",
        "alertas:leer",
    ),
    "Proveedor": ("pedido_proveedor:confirmar",),
}

ADMIN_EMAIL = "admin@ds.gt"
ADMIN_PASSWORD_INICIAL = "CambiarAdmin123"  # Solo para bootstrap local; rotar tras el primer login.
ADMIN_NOMBRE = "Administrador del Sistema"

PARAMETROS_INICIALES: dict[str, object] = {
    "ml.mape_umbral": 12.0,
    "ml.periodos_consecutivos": 3,
}


def _get_or_create_permiso(session: Session, codigo: str, descripcion: str) -> Permiso:
    permiso = session.query(Permiso).filter_by(codigo=codigo).one_or_none()
    if permiso is None:
        permiso = Permiso(codigo=codigo, descripcion=descripcion)
        session.add(permiso)
        session.flush()
    return permiso


def _get_or_create_rol(session: Session, nombre: str, descripcion: str) -> Rol:
    rol = session.query(Rol).filter_by(nombre=nombre).one_or_none()
    if rol is None:
        rol = Rol(nombre=nombre, descripcion=descripcion)
        session.add(rol)
        session.flush()
    return rol


def seed_roles_y_permisos(session: Session) -> dict[str, Rol]:
    permisos_por_codigo = {
        codigo: _get_or_create_permiso(session, codigo, descripcion)
        for codigo, descripcion in PERMISOS.items()
    }
    roles_por_nombre: dict[str, Rol] = {}
    for nombre, descripcion in ROLES.items():
        rol = _get_or_create_rol(session, nombre, descripcion)
        permisos_asignados = {permiso.codigo for permiso in rol.permisos}
        for codigo in MATRIZ_ROL_PERMISO[nombre]:
            if codigo not in permisos_asignados:
                rol.permisos.append(permisos_por_codigo[codigo])
        roles_por_nombre[nombre] = rol
    return roles_por_nombre


def seed_admin(session: Session, roles_por_nombre: dict[str, Rol]) -> Usuario:
    admin = session.query(Usuario).filter_by(email=ADMIN_EMAIL).one_or_none()
    if admin is None:
        admin = Usuario(
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD_INICIAL),
            nombre_completo=ADMIN_NOMBRE,
        )
        session.add(admin)
        session.flush()
    if roles_por_nombre["Admin"] not in admin.roles:
        admin.roles.append(roles_por_nombre["Admin"])
    return admin


def seed_parametros_sistema(session: Session) -> None:
    for clave, valor in PARAMETROS_INICIALES.items():
        parametro = session.get(ParametroSistema, clave)
        if parametro is None:
            session.add(ParametroSistema(clave=clave, valor=valor))
        else:
            parametro.valor = valor


def run() -> None:
    session = get_sessionmaker()()
    try:
        roles_por_nombre = seed_roles_y_permisos(session)
        seed_admin(session, roles_por_nombre)
        seed_parametros_sistema(session)
        session.commit()
        print("[OK] Seeds de roles, permisos, usuario admin y parametros_sistema aplicados.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
