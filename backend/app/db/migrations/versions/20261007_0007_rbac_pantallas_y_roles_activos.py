"""rbac en base de datos: pantallas, pantallas_permisos y roles activables (ADR-19)

Lleva a la BD lo que estaba quemado en el frontend (`PERMISOS_VISTA`, `NAV`): qué pantalla
exige qué permiso. Añade a `roles` (activo, es_sistema, requiere_proveedor, color,
pantalla_inicio_id) y a `permisos` (modulo, activo). Los datos iniciales replican el menú
vigente, de modo que desplegar la migración no cambia lo que ve ningún usuario.

Los roles heredados (Encargados y Proveedor) se desactivan solo si NO tienen usuarios
asignados; así nadie pierde el acceso al migrar. Se reactivan desde la matriz.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES_HEREDADOS = (
    'EncargadoInventario',
    'EncargadoVentas',
    'EncargadoBodega',
    'EncargadoCompras',
    'Proveedor',
)

COLORES = {
    'Administrador': 'bad',
    'Gerente': 'brand',
    'EncargadoVentas': 'good',
    'EncargadoInventario': 'warn',
    'EncargadoBodega': 'warn',
    'EncargadoCompras': 'brand',
    'Liquidador': 'good',
}

PERMISO_ROLES = ('roles:gestionar', 'Alta de roles, activación y matriz de permisos por rol (ADR-19).')

# (clave, etiqueta, ruta, ruta_prefijo, grupo, orden, permisos que la habilitan)
PANTALLAS = (
    ('dashboard', 'Dashboard de Ventas', '/', None, 'Ventas', 10,
     ('carga_ruta:generar', 'carga_ruta:aprobar')),
    ('monitoreo', 'Monitoreo de Modelos', '/monitoreo', None, 'Analítica', 20,
     ('ml:metricas:leer',)),
    ('compras', 'Abastecimiento', '/compras', None, 'Inventario', 30,
     ('pedido_proveedor:gestionar', 'pedido_proveedor:confirmar', 'inventario:ajustar')),
    ('inventario', 'Inventario y Kardex', '/inventario', None, 'Inventario', 40,
     ('inventario:leer',)),
    ('productos', 'Productos', '/productos', None, 'Inventario', 50, ('inventario:leer',)),
    ('liquidacion', 'Liquidación Diaria', '/ventas/liquidacion', None, 'Ventas', 60,
     ('liquidaciones:registrar',)),
    ('liquidaciones', 'Historial de Liquidaciones', '/ventas/liquidaciones', None, 'Ventas', 70,
     ('liquidaciones:leer',)),
    ('catalogos', 'Rutas', '/catalogos/rutas', '/catalogos', 'Catálogos', 80,
     ('catalogos:leer',)),
    ('etl', 'Carga de Datos (ETL)', '/etl', None, 'Datos', 90, ('etl:cargar',)),
    ('politica_datos', 'Política de Datos', '/politica-datos', None, 'Datos', 100,
     ('etl:configurar',)),
    ('reportes', 'Reportes', '/reportes', None, 'Analítica', 110, ('reportes:leer',)),
    ('usuarios', 'Usuarios y Roles', '/usuarios', None, 'Administración', 120,
     ('usuarios:gestionar',)),
)


def _lit(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pantallas',
    sa.Column('id', sa.SmallInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('clave', sa.String(length=40), nullable=False),
    sa.Column('etiqueta', sa.String(length=80), nullable=False),
    sa.Column('ruta', sa.String(length=120), nullable=False),
    sa.Column('ruta_prefijo', sa.String(length=120), nullable=True),
    sa.Column('grupo', sa.String(length=40), server_default='General', nullable=False),
    sa.Column('orden', sa.SmallInteger(), server_default='100', nullable=False),
    sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("ruta LIKE '/%'", name=op.f('ck_pantallas_ruta_absoluta')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pantallas')),
    sa.UniqueConstraint('clave', name=op.f('uq_pantallas_clave'))
    )
    op.create_table('pantallas_permisos',
    sa.Column('pantalla_id', sa.SmallInteger(), nullable=False),
    sa.Column('permiso_id', sa.SmallInteger(), nullable=False),
    sa.ForeignKeyConstraint(['pantalla_id'], ['pantallas.id'], name=op.f('fk_pantallas_permisos_pantalla_id_pantallas'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['permiso_id'], ['permisos.id'], name=op.f('fk_pantallas_permisos_permiso_id_permisos'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('pantalla_id', 'permiso_id', name=op.f('pk_pantallas_permisos'))
    )

    op.add_column('permisos', sa.Column('modulo', sa.String(length=40), server_default='general', nullable=False))
    op.add_column('permisos', sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('roles', sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('roles', sa.Column('es_sistema', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('roles', sa.Column('requiere_proveedor', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('roles', sa.Column('color', sa.String(length=20), server_default='neutral', nullable=False))
    op.add_column('roles', sa.Column('pantalla_inicio_id', sa.SmallInteger(), nullable=True))
    op.create_foreign_key(op.f('fk_roles_pantalla_inicio_id_pantallas'), 'roles', 'pantallas', ['pantalla_inicio_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint(
        op.f('ck_roles_color_valido'), 'roles',
        "color IN ('bad', 'brand', 'good', 'warn', 'neutral')",
    )

    # --- datos iniciales (equivalentes al menú vigente) ---
    op.execute("UPDATE permisos SET modulo = split_part(codigo, ':', 1)")
    codigo, descripcion = PERMISO_ROLES
    op.execute(
        f"INSERT INTO permisos (codigo, descripcion, modulo) "
        f"VALUES ({_lit(codigo)}, {_lit(descripcion)}, 'roles') ON CONFLICT (codigo) DO NOTHING"
    )
    op.execute(
        "INSERT INTO roles_permisos (rol_id, permiso_id) "
        "SELECT r.id, p.id FROM roles r, permisos p "
        f"WHERE r.nombre = 'Administrador' AND p.codigo = {_lit(codigo)} ON CONFLICT DO NOTHING"
    )

    for nombre, color in COLORES.items():
        op.execute(f"UPDATE roles SET color = {_lit(color)} WHERE nombre = {_lit(nombre)}")
    op.execute("UPDATE roles SET es_sistema = true WHERE nombre = 'Administrador'")
    op.execute("UPDATE roles SET requiere_proveedor = true WHERE nombre = 'Proveedor'")

    for clave, etiqueta, ruta, prefijo, grupo, orden, permisos in PANTALLAS:
        op.execute(
            "INSERT INTO pantallas (clave, etiqueta, ruta, ruta_prefijo, grupo, orden) VALUES ("
            f"{_lit(clave)}, {_lit(etiqueta)}, {_lit(ruta)}, "
            f"{_lit(prefijo) if prefijo else 'NULL'}, {_lit(grupo)}, {orden}) "
            "ON CONFLICT (clave) DO NOTHING"
        )
        for permiso in permisos:
            op.execute(
                "INSERT INTO pantallas_permisos (pantalla_id, permiso_id) "
                "SELECT pa.id, pe.id FROM pantallas pa, permisos pe "
                f"WHERE pa.clave = {_lit(clave)} AND pe.codigo = {_lit(permiso)} "
                "ON CONFLICT DO NOTHING"
            )

    # Desactiva los roles heredados que nadie usa; los que tienen usuarios siguen activos.
    nombres = ', '.join(_lit(n) for n in ROLES_HEREDADOS)
    op.execute(
        f"UPDATE roles SET activo = false WHERE nombre IN ({nombres}) "
        "AND NOT EXISTS (SELECT 1 FROM usuarios_roles ur WHERE ur.rol_id = roles.id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM roles_permisos WHERE permiso_id IN (SELECT id FROM permisos WHERE codigo = 'roles:gestionar')")
    op.execute("DELETE FROM permisos WHERE codigo = 'roles:gestionar'")
    op.drop_constraint(op.f('ck_roles_color_valido'), 'roles', type_='check')
    op.drop_constraint(op.f('fk_roles_pantalla_inicio_id_pantallas'), 'roles', type_='foreignkey')
    op.drop_column('roles', 'pantalla_inicio_id')
    op.drop_column('roles', 'color')
    op.drop_column('roles', 'requiere_proveedor')
    op.drop_column('roles', 'es_sistema')
    op.drop_column('roles', 'activo')
    op.drop_column('permisos', 'activo')
    op.drop_column('permisos', 'modulo')
    op.drop_table('pantallas_permisos')
    op.drop_table('pantallas')
