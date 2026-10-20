"""Recepción documentada y estado recibido_parcial.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_pedidos_proveedor_estado_valido"), "pedidos_proveedor", type_="check")
    op.alter_column("pedidos_proveedor", "estado", type_=sa.String(20))
    op.create_check_constraint(op.f("ck_pedidos_proveedor_estado_valido"), "pedidos_proveedor",
        "estado IN ('borrador','enviado','confirmado','recibido','recibido_parcial','cancelado')")
    op.drop_constraint(op.f("ck_kardex_referencia_tipo_valida"), "kardex", type_="check")
    op.create_check_constraint(op.f("ck_kardex_referencia_tipo_valida"), "kardex",
        "referencia_tipo IS NULL OR referencia_tipo IN ('carga_ruta','pedido','ajuste','etl','recepcion')")
    op.create_table("recepciones_mercaderia",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("pedido_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pedidos_proveedor.id", ondelete="RESTRICT"), unique=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("documento_referencia", sa.String(150), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    # Evita perder recepciones o convertir silenciosamente un parcial en una entrega completa.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM recepciones_mercaderia) THEN "
               "RAISE EXCEPTION 'Existen recepciones: no se puede revertir sin perder datos'; "
               "END IF; END $$")
    op.drop_table("recepciones_mercaderia")
    op.drop_constraint(op.f("ck_kardex_referencia_tipo_valida"), "kardex", type_="check")
    op.create_check_constraint(op.f("ck_kardex_referencia_tipo_valida"), "kardex",
        "referencia_tipo IS NULL OR referencia_tipo IN ('carga_ruta','pedido','ajuste','etl')")
    op.drop_constraint(op.f("ck_pedidos_proveedor_estado_valido"), "pedidos_proveedor", type_="check")
    op.alter_column("pedidos_proveedor", "estado", type_=sa.String(12))
    op.create_check_constraint(op.f("ck_pedidos_proveedor_estado_valido"), "pedidos_proveedor",
        "estado IN ('borrador','enviado','confirmado','recibido','cancelado')")
