"""contraseña temporal: usuarios.debe_cambiar_password

Marca las cuentas cuya contraseña la fijó un administrador (alta o restablecimiento): el
usuario debe cambiarla en su siguiente ingreso. Las cuentas existentes quedan en `false`,
así que desplegar la migración no obliga a nadie a cambiarla.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'usuarios',
        sa.Column('debe_cambiar_password', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('usuarios', 'debe_cambiar_password')
