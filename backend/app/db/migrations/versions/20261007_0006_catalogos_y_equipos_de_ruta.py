"""catalogos y equipos de ruta (M02, ADR-18)

Presentación en paquete de `productos`, alias de Excel, `empleados` y `equipo_ruta`.
Todo es aditivo: no cambia datos existentes ni la semántica de `rutas.vendedor_id`.
El autogenerate no detecta CHECK sobre columnas añadidas: se declaran a mano.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07 05:29:54.885035

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('empleados',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('nombre_completo', sa.String(length=150), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=True),
    sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_empleados_usuario_id_usuarios'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_empleados')),
    sa.UniqueConstraint('usuario_id', name=op.f('uq_empleados_usuario_id'))
    )
    op.create_table('producto_alias_excel',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('producto_id', sa.UUID(), nullable=False),
    sa.Column('alias', sa.String(length=80), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name=op.f('fk_producto_alias_excel_producto_id_productos'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_producto_alias_excel')),
    sa.UniqueConstraint('alias', name=op.f('uq_producto_alias_excel_alias'))
    )
    op.create_index(op.f('ix_producto_alias_excel_producto_id'), 'producto_alias_excel', ['producto_id'], unique=False)
    op.create_table('equipo_ruta',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ruta_id', sa.UUID(), nullable=False),
    sa.Column('empleado_id', sa.UUID(), nullable=False),
    sa.Column('rol_en_ruta', sa.String(length=10), nullable=False),
    sa.Column('porcentaje_reparto', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=False),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("rol_en_ruta IN ('vendedor', 'chofer', 'auxiliar')", name=op.f('ck_equipo_ruta_rol_en_ruta_valido')),
    sa.CheckConstraint('porcentaje_reparto BETWEEN 0 AND 100', name=op.f('ck_equipo_ruta_porcentaje_en_rango')),
    sa.CheckConstraint('vigente_hasta IS NULL OR vigente_desde <= vigente_hasta', name=op.f('ck_equipo_ruta_vigencia_coherente')),
    sa.ForeignKeyConstraint(['empleado_id'], ['empleados.id'], name=op.f('fk_equipo_ruta_empleado_id_empleados'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['ruta_id'], ['rutas.id'], name=op.f('fk_equipo_ruta_ruta_id_rutas'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_equipo_ruta'))
    )
    op.create_index(op.f('ix_equipo_ruta_empleado_id'), 'equipo_ruta', ['empleado_id'], unique=False)
    op.create_index(op.f('ix_equipo_ruta_ruta_id'), 'equipo_ruta', ['ruta_id'], unique=False)
    op.create_index('uq_equipo_ruta_empleado_vigente', 'equipo_ruta', ['ruta_id', 'empleado_id'], unique=True, postgresql_where=sa.text('vigente_hasta IS NULL'))
    op.create_index('uq_equipo_ruta_vendedor_vigente', 'equipo_ruta', ['ruta_id'], unique=True, postgresql_where=sa.text("rol_en_ruta = 'vendedor' AND vigente_hasta IS NULL"))
    op.add_column('productos', sa.Column('unidades_por_paquete', sa.SmallInteger(), server_default=sa.text('1'), nullable=False))
    op.add_column('productos', sa.Column('medida_ml', sa.Integer(), nullable=True))
    op.add_column('productos', sa.Column('sabor', sa.String(length=60), nullable=True))
    op.create_check_constraint(op.f('ck_productos_unidades_por_paquete_positivas'), 'productos', 'unidades_por_paquete > 0')
    op.create_check_constraint(op.f('ck_productos_medida_ml_positiva'), 'productos', 'medida_ml IS NULL OR medida_ml > 0')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_productos_medida_ml_positiva'), 'productos', type_='check')
    op.drop_constraint(op.f('ck_productos_unidades_por_paquete_positivas'), 'productos', type_='check')
    op.drop_column('productos', 'sabor')
    op.drop_column('productos', 'medida_ml')
    op.drop_column('productos', 'unidades_por_paquete')
    op.drop_index('uq_equipo_ruta_vendedor_vigente', table_name='equipo_ruta', postgresql_where=sa.text("rol_en_ruta = 'vendedor' AND vigente_hasta IS NULL"))
    op.drop_index('uq_equipo_ruta_empleado_vigente', table_name='equipo_ruta', postgresql_where=sa.text('vigente_hasta IS NULL'))
    op.drop_index(op.f('ix_equipo_ruta_ruta_id'), table_name='equipo_ruta')
    op.drop_index(op.f('ix_equipo_ruta_empleado_id'), table_name='equipo_ruta')
    op.drop_table('equipo_ruta')
    op.drop_index(op.f('ix_producto_alias_excel_producto_id'), table_name='producto_alias_excel')
    op.drop_table('producto_alias_excel')
    op.drop_table('empleados')
