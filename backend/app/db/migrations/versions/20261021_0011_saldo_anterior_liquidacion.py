"""Saldo anterior por línea de liquidación (lo devuelto en el último cierre de la ruta).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_TABLA = "liquidacion_detalles"
_NO_NEGATIVOS = (
    "{s}cantidad_cargada >= 0 AND cantidad_vendida >= 0 AND cantidad_devuelta >= 0 "
    "AND cantidad_merma >= 0 AND precio_unitario >= 0 AND monto_total >= 0"
)


def _soltar_checks() -> None:
    op.drop_constraint(op.f("ck_liquidacion_detalles_valores_no_negativos"), _TABLA, type_="check")
    op.drop_constraint(
        op.f("ck_liquidacion_detalles_unidades_no_exceden_cargada"), _TABLA, type_="check"
    )


def _crear_checks(con_saldo: bool) -> None:
    op.create_check_constraint(
        op.f("ck_liquidacion_detalles_valores_no_negativos"),
        _TABLA,
        _NO_NEGATIVOS.format(s="saldo_anterior >= 0 AND " if con_saldo else ""),
    )
    op.create_check_constraint(
        op.f("ck_liquidacion_detalles_unidades_no_exceden_cargada"),
        _TABLA,
        "cantidad_vendida + cantidad_devuelta + cantidad_merma <= "
        + ("saldo_anterior + cantidad_cargada" if con_saldo else "cantidad_cargada"),
    )


def upgrade() -> None:
    op.add_column(
        _TABLA,
        sa.Column(
            "saldo_anterior",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    _soltar_checks()
    _crear_checks(con_saldo=True)


def downgrade() -> None:
    _soltar_checks()
    op.drop_column(_TABLA, "saldo_anterior")
    _crear_checks(con_saldo=False)
