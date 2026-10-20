"""Encabezado FEL y unicidad de facturas en recepciones.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No se inventan datos FEL para documentos históricos: sus campos quedan nulos.
    op.alter_column("recepciones_mercaderia", "documento_referencia", nullable=True)
    for nombre, tipo in (
        ("serie", sa.String(50)),
        ("numero", sa.String(50)),
        ("numero_autorizacion", postgresql.UUID(as_uuid=True)),
        ("fecha_emision", sa.Date()),
        ("condicion_pago", sa.String(150)),
        ("serie_admin", sa.String(50)),
        ("numero_admin", sa.String(50)),
    ):
        op.add_column("recepciones_mercaderia", sa.Column(nombre, tipo, nullable=True))
    op.create_unique_constraint(
        "uq_recepciones_autorizacion", "recepciones_mercaderia", ["numero_autorizacion"]
    )
    op.create_unique_constraint(
        "uq_recepciones_serie_numero", "recepciones_mercaderia", ["serie", "numero"]
    )


def downgrade() -> None:
    # Conserva una referencia legible al volver al esquema anterior.
    op.execute("UPDATE recepciones_mercaderia SET documento_referencia = "
               "'FEL ' || serie || '-' || numero || ' / ' || numero_autorizacion::text "
               "WHERE documento_referencia IS NULL")
    op.drop_constraint("uq_recepciones_serie_numero", "recepciones_mercaderia", type_="unique")
    op.drop_constraint("uq_recepciones_autorizacion", "recepciones_mercaderia", type_="unique")
    for nombre in ("numero_admin", "serie_admin", "condicion_pago", "fecha_emision",
                   "numero_autorizacion", "numero", "serie"):
        op.drop_column("recepciones_mercaderia", nombre)
    op.alter_column("recepciones_mercaderia", "documento_referencia", nullable=False)
