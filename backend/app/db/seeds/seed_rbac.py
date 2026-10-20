"""Seeds iniciales: roles, permisos (matriz 1.4), usuario admin y `parametros_sistema`.

Idempotente: puede ejecutarse varias veces sin duplicar filas ni pisar el hash de
contraseña del admin si ya existe. Tras la ADR-19 la BD es la fuente de verdad de la matriz:
el seed solo CREA lo que falta (la matriz por defecto se aplica únicamente a roles y pantallas
nuevos) y nunca revierte lo editado desde la pantalla de permisos. La excepción es el rol de
sistema (Administrador), que siempre conserva todos los permisos.

Uso (desde `backend/`, con el venv activo):
    python -m app.db.seeds.seed_rbac
"""

from sqlalchemy.orm import Session

from app.core import parametros
from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.domain.enums import ColorRol, NombreRol
from app.domain.models.auth import Pantalla, Permiso, Rol, Usuario
from app.domain.models.ml import ParametroSistema

ROLES: dict[str, str] = {
    NombreRol.ADMINISTRADOR: "Acceso total al sistema.",
    NombreRol.ENCARGADO_INVENTARIO: "Carga de histórico y gestión de existencias.",
    NombreRol.ENCARGADO_VENTAS: "Generación y aprobación de cargas de ruta.",
    NombreRol.ENCARGADO_BODEGA: "Despacho de cargas y ajuste de inventario.",
    NombreRol.ENCARGADO_COMPRAS: "Gestión de pedidos a proveedores.",
    NombreRol.GERENTE: "Aprobación de cargas y monitoreo de modelos ML.",
    NombreRol.PROVEEDOR: "Confirmación de pedidos propios (acceso restringido por proveedor_id).",
    NombreRol.LIQUIDADOR: (
        "Responsable de registrar y cerrar la liquidación diaria por ruta y vendedor (ADR-14)."
    ),
}

PERMISOS: dict[str, str] = {
    "usuarios:gestionar": "Alta, baja y edición de usuarios y roles.",
    "etl:cargar": "Ingesta de histórico de ventas desde Excel.",
    "prediccion:consultar": "Consulta de pronósticos de demanda.",
    "carga_ruta:generar": "Generación de planes de carga de ruta.",
    "carga_ruta:aprobar": "Aprobación o rechazo de planes de carga.",
    "carga_ruta:revertir": "Reversión de cargas aprobadas (solo Administrador).",
    "carga_ruta:despachar": "Confirmación de despacho (kardex de salida).",
    "inventario:leer": "Consulta de existencias.",
    "inventario:ajustar": "Ajustes manuales de existencias.",
    "productos:crear": "Alta de productos en el catálogo (ADR-16).",
    "productos:editar": "Edición de datos de productos: precio, costo, mínimo, categoría (ADR-16).",
    "productos:eliminar": "Baja lógica y reactivación de productos (ADR-16).",
    "pedido_proveedor:gestionar": "Creación y edición de pedidos a proveedores.",
    "pedido_proveedor:confirmar": "Confirmación de pedidos por el proveedor.",
    "ml:metricas:leer": "Consulta de métricas y degradación de modelos.",
    "ml:reentrenar": "Solicitud de reentrenamiento de modelos.",
    "alertas:leer": "Consulta de alertas del sistema.",
    "reportes:leer": "Reportes gerenciales: rotación, quiebres, comisiones y exportación.",
    "liquidaciones:registrar": "Registro y edición de borradores de la liquidación diaria.",
    "liquidaciones:cerrar": "Cierre de la liquidación diaria (alimenta el modelo).",
    "liquidaciones:corregir": "Corrección y anulación de liquidaciones; umbral de caja.",
    "liquidaciones:leer": "Consulta del historial de liquidaciones y su cuadre de caja.",
    "etl:configurar": "Cierre del arranque ETL y fuente de reentrenamiento (política de datos).",
    "bitacora:leer": "Consulta de la bitácora de auditoría del sistema (ADR-15).",
    "catalogos:leer": "Consulta de rutas, empleados y equipos de ruta (M02, ADR-18).",
    "catalogos:gestionar": "Alta y edición de rutas, empleados y equipos de ruta (M02, ADR-18).",
    "roles:gestionar": "Alta de roles, activación y matriz de permisos por rol (ADR-19).",
}

# Atributos de presentación/estado de cada rol (ADR-19). Los roles heredados nacen inactivos:
# se pueden reactivar desde la matriz.
ROLES_ACTIVOS: frozenset[str] = frozenset(
    {NombreRol.ADMINISTRADOR, NombreRol.GERENTE, NombreRol.LIQUIDADOR}
)
ROL_COLOR: dict[str, ColorRol] = {
    NombreRol.ADMINISTRADOR: ColorRol.ROJO,
    NombreRol.GERENTE: ColorRol.AZUL,
    NombreRol.ENCARGADO_VENTAS: ColorRol.VERDE,
    NombreRol.ENCARGADO_INVENTARIO: ColorRol.AMBAR,
    NombreRol.ENCARGADO_BODEGA: ColorRol.AMBAR,
    NombreRol.ENCARGADO_COMPRAS: ColorRol.AZUL,
    NombreRol.LIQUIDADOR: ColorRol.VERDE,
}

# (clave, etiqueta, ruta, ruta_prefijo, grupo, orden, permisos que la habilitan: basta UNO)
PANTALLAS: tuple[tuple[str, str, str, str | None, str, int, tuple[str, ...]], ...] = (
    (
        "dashboard",
        "Dashboard de Ventas",
        "/",
        None,
        "Ventas",
        10,
        ("carga_ruta:generar", "carga_ruta:aprobar"),
    ),
    (
        "monitoreo",
        "Monitoreo de Modelos",
        "/monitoreo",
        None,
        "Analítica",
        20,
        ("ml:metricas:leer",),
    ),
    (
        "compras",
        "Abastecimiento",
        "/compras",
        None,
        "Inventario",
        30,
        ("pedido_proveedor:gestionar", "pedido_proveedor:confirmar", "inventario:ajustar"),
    ),
    (
        "inventario",
        "Inventario y Kardex",
        "/inventario",
        None,
        "Inventario",
        40,
        ("inventario:leer",),
    ),
    ("productos", "Productos", "/productos", None, "Inventario", 50, ("inventario:leer",)),
    (
        "liquidacion",
        "Liquidación Diaria",
        "/ventas/liquidacion",
        None,
        "Ventas",
        60,
        ("liquidaciones:registrar",),
    ),
    (
        "liquidaciones",
        "Historial de Liquidaciones",
        "/ventas/liquidaciones",
        None,
        "Ventas",
        70,
        ("liquidaciones:leer",),
    ),
    ("catalogos", "Rutas", "/catalogos/rutas", "/catalogos", "Catálogos", 80, ("catalogos:leer",)),
    ("etl", "Carga de Datos (ETL)", "/etl", None, "Datos", 90, ("etl:cargar",)),
    (
        "politica_datos",
        "Política de Datos",
        "/politica-datos",
        None,
        "Datos",
        100,
        ("etl:configurar",),
    ),
    ("reportes", "Reportes", "/reportes", None, "Analítica", 110, ("reportes:leer",)),
    (
        "usuarios",
        "Usuarios y Roles",
        "/usuarios",
        None,
        "Administración",
        120,
        ("usuarios:gestionar",),
    ),
)

# Matriz 1.4 de la especificación (columna Worker se excluye: no es un rol de login).
MATRIZ_ROL_PERMISO: dict[str, tuple[str, ...]] = {
    NombreRol.ADMINISTRADOR: tuple(PERMISOS),
    NombreRol.ENCARGADO_INVENTARIO: (
        "etl:cargar",
        "prediccion:consultar",
        "inventario:leer",
        "inventario:ajustar",
        "productos:crear",
        "productos:editar",
        "productos:eliminar",
        "catalogos:leer",
        "alertas:leer",
    ),
    NombreRol.ENCARGADO_VENTAS: (
        "etl:cargar",
        "prediccion:consultar",
        "carga_ruta:generar",
        "carga_ruta:aprobar",
        "inventario:leer",
        "alertas:leer",
    ),
    NombreRol.ENCARGADO_BODEGA: (
        "carga_ruta:despachar",
        "inventario:leer",
        "inventario:ajustar",
        "alertas:leer",
    ),
    NombreRol.ENCARGADO_COMPRAS: (
        "prediccion:consultar",
        "inventario:leer",
        "pedido_proveedor:gestionar",
        "alertas:leer",
    ),
    NombreRol.GERENTE: (
        "reportes:leer",
        "prediccion:consultar",
        "carga_ruta:aprobar",
        "inventario:leer",
        "ml:metricas:leer",
        "ml:reentrenar",
        "alertas:leer",
        "liquidaciones:leer",
        "catalogos:leer",
    ),
    NombreRol.PROVEEDOR: ("pedido_proveedor:confirmar",),
    NombreRol.LIQUIDADOR: (
        "liquidaciones:registrar",
        "liquidaciones:cerrar",
        "liquidaciones:leer",
    ),
}

ADMIN_EMAIL = "admin@ds.gt"
ADMIN_PASSWORD_INICIAL = "CambiarAdmin123"  # Solo para bootstrap local; rotar tras el primer login.
ADMIN_NOMBRE = "Administrador del Sistema"

PARAMETROS_INICIALES: dict[str, object] = {
    "ml.mape_umbral": 12.0,
    "ml.periodos_consecutivos": 3,
}

# ADR-14: los administra el negocio; el seed solo los crea si faltan (nunca pisa un cambio).
PARAMETROS_POR_DEFECTO: dict[str, object] = {
    parametros.CARGA_EXCEL_HABILITADA: parametros.CARGA_EXCEL_HABILITADA_POR_DEFECTO,
    parametros.FUENTE_REENTRENAMIENTO: parametros.FUENTE_REENTRENAMIENTO_POR_DEFECTO,
    parametros.UMBRAL_DIFERENCIA_CAJA: float(parametros.UMBRAL_DIFERENCIA_CAJA_POR_DEFECTO),
}


def _modulo(codigo: str) -> str:
    return codigo.split(":", 1)[0]


def _get_or_create_permiso(session: Session, codigo: str, descripcion: str) -> Permiso:
    permiso = session.query(Permiso).filter_by(codigo=codigo).one_or_none()
    if permiso is None:
        permiso = Permiso(codigo=codigo, descripcion=descripcion, modulo=_modulo(codigo))
        session.add(permiso)
        session.flush()
    return permiso


def _get_or_create_rol(session: Session, nombre: str, descripcion: str) -> tuple[Rol, bool]:
    """Devuelve `(rol, creado)`; los atributos de ADR-19 solo se fijan al crear el rol."""
    rol = session.query(Rol).filter_by(nombre=nombre).one_or_none()
    if rol is not None:
        return rol, False
    rol = Rol(
        nombre=nombre,
        descripcion=descripcion,
        activo=nombre in ROLES_ACTIVOS,
        es_sistema=nombre == NombreRol.ADMINISTRADOR,
        requiere_proveedor=nombre == NombreRol.PROVEEDOR,
        color=ROL_COLOR.get(nombre, ColorRol.NEUTRO).value,
    )
    session.add(rol)
    session.flush()
    return rol, True


def seed_roles_y_permisos(session: Session) -> dict[str, Rol]:
    permisos_por_codigo = {
        codigo: _get_or_create_permiso(session, codigo, descripcion)
        for codigo, descripcion in PERMISOS.items()
    }
    roles_por_nombre: dict[str, Rol] = {}
    for nombre, descripcion in ROLES.items():
        rol, creado = _get_or_create_rol(session, nombre, descripcion)
        asignados = {permiso.codigo for permiso in rol.permisos}
        # Rol nuevo: matriz por defecto. Rol de sistema: siempre completo. El resto no se toca.
        if creado or rol.es_sistema:
            for codigo in MATRIZ_ROL_PERMISO[nombre]:
                if codigo not in asignados:
                    rol.permisos.append(permisos_por_codigo[codigo])
        roles_por_nombre[nombre] = rol
    return roles_por_nombre


def seed_pantallas(session: Session) -> None:
    """Crea las pantallas que falten con sus permisos; las existentes no se modifican."""
    for clave, etiqueta, ruta, prefijo, grupo, orden, codigos in PANTALLAS:
        if session.query(Pantalla).filter_by(clave=clave).one_or_none() is not None:
            continue
        pantalla = Pantalla(
            clave=clave,
            etiqueta=etiqueta,
            ruta=ruta,
            ruta_prefijo=prefijo,
            grupo=grupo,
            orden=orden,
        )
        pantalla.permisos = [
            session.query(Permiso).filter_by(codigo=codigo).one() for codigo in codigos
        ]
        session.add(pantalla)
    session.flush()


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
    if roles_por_nombre[NombreRol.ADMINISTRADOR] not in admin.roles:
        admin.roles.append(roles_por_nombre[NombreRol.ADMINISTRADOR])
    return admin


def seed_parametros_sistema(session: Session) -> None:
    for clave, valor in PARAMETROS_INICIALES.items():
        parametro = session.get(ParametroSistema, clave)
        if parametro is None:
            session.add(ParametroSistema(clave=clave, valor=valor))
        else:
            parametro.valor = valor
    for clave, valor in PARAMETROS_POR_DEFECTO.items():
        if session.get(ParametroSistema, clave) is None:
            session.add(ParametroSistema(clave=clave, valor=valor))


def run() -> None:
    session = get_sessionmaker()()
    try:
        roles_por_nombre = seed_roles_y_permisos(session)
        seed_pantallas(session)
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
