"""Bitácora de auditoría y respaldo (ADR-15).

Tabla `bitacora` append-only: un trigger impide UPDATE, DELETE y TRUNCATE (autogenerate no
detecta triggers: escrito a mano).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('bitacora',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('ocurrido_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('nivel', sa.String(length=7), nullable=False),
    sa.Column('origen', sa.String(length=10), nullable=False),
    sa.Column('operacion', sa.String(length=10), nullable=False),
    sa.Column('accion', sa.String(length=200), nullable=False),
    sa.Column('resultado', sa.String(length=5), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('request_id', sa.String(length=36), nullable=True),
    sa.Column('metodo', sa.String(length=10), nullable=True),
    sa.Column('ruta', sa.String(length=300), nullable=True),
    sa.Column('status_code', sa.SmallInteger(), nullable=True),
    sa.Column('duracion_ms', sa.Integer(), nullable=True),
    sa.Column('parametros', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('codigo_error', sa.String(length=60), nullable=True),
    sa.Column('mensaje', sa.Text(), nullable=True),
    sa.CheckConstraint("nivel IN ('INFO', 'WARNING', 'ERROR')", name=op.f('ck_bitacora_nivel_valido')),
    sa.CheckConstraint("origen IN ('http', 'servicio', 'worker')", name=op.f('ck_bitacora_origen_valido')),
    sa.CheckConstraint("operacion IN ('lectura', 'escritura')", name=op.f('ck_bitacora_operacion_valida')),
    sa.CheckConstraint("resultado IN ('exito', 'error')", name=op.f('ck_bitacora_resultado_valido')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bitacora'))
    )
    op.create_index(op.f('ix_bitacora_ocurrido_en'), 'bitacora', ['ocurrido_en'], unique=False)
    op.create_index(op.f('ix_bitacora_usuario_id'), 'bitacora', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_bitacora_accion'), 'bitacora', ['accion'], unique=False)
    op.create_index(op.f('ix_bitacora_request_id'), 'bitacora', ['request_id'], unique=False)

    op.execute("""
        CREATE FUNCTION bitacora_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La bitácora es de solo inserción (%)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_bitacora_inmutable
        BEFORE UPDATE OR DELETE ON bitacora
        FOR EACH ROW EXECUTE FUNCTION bitacora_inmutable()
    """)
    op.execute("""
        CREATE TRIGGER trg_bitacora_sin_truncate
        BEFORE TRUNCATE ON bitacora
        FOR EACH STATEMENT EXECUTE FUNCTION bitacora_inmutable()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER trg_bitacora_sin_truncate ON bitacora")
    op.execute("DROP TRIGGER trg_bitacora_inmutable ON bitacora")
    op.execute("DROP FUNCTION bitacora_inmutable()")
    op.drop_index(op.f('ix_bitacora_request_id'), table_name='bitacora')
    op.drop_index(op.f('ix_bitacora_accion'), table_name='bitacora')
    op.drop_index(op.f('ix_bitacora_usuario_id'), table_name='bitacora')
    op.drop_index(op.f('ix_bitacora_ocurrido_en'), table_name='bitacora')
    op.drop_table('bitacora')
