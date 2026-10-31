"""Recepción en el menú RBAC y orden de los grupos.

Revision ID: 0012
Revises: 0011
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ORDEN_NUEVO = {
    "dashboard": 10,
    "liquidacion": 20,
    "liquidaciones": 30,
    "compras": 40,
    "recepcion": 50,
    "inventario": 60,
    "productos": 70,
    "reportes": 80,
    "monitoreo": 90,
    "catalogos": 100,
    "etl": 110,
    "politica_datos": 120,
    "usuarios": 130,
}
ORDEN_ANTERIOR = {
    "dashboard": 10,
    "monitoreo": 20,
    "compras": 30,
    "inventario": 40,
    "productos": 50,
    "liquidacion": 60,
    "liquidaciones": 70,
    "catalogos": 80,
    "etl": 90,
    "politica_datos": 100,
    "reportes": 110,
    "usuarios": 120,
}


def _ordenar(ordenes: dict[str, int]) -> None:
    for clave, orden in ordenes.items():
        op.execute(
            sa.text("UPDATE pantallas SET orden = :orden WHERE clave = :clave").bindparams(
                clave=clave, orden=orden
            )
        )


def upgrade() -> None:
    op.execute(
        "INSERT INTO pantallas (clave, etiqueta, ruta, ruta_prefijo, grupo, orden) "
        "VALUES ('recepcion', 'Recepción de mercadería', '/recepcion', NULL, 'Inventario', 50)"
    )
    # Los roles acceden a través de sus permisos vigentes, sin asignaciones por pantalla.
    op.execute(
        "INSERT INTO pantallas_permisos (pantalla_id, permiso_id) "
        "SELECT pa.id, pe.id FROM pantallas pa, permisos pe "
        "WHERE pa.clave = 'recepcion' AND pe.codigo = 'inventario:ajustar'"
    )
    _ordenar(ORDEN_NUEVO)


def downgrade() -> None:
    # La relación de permisos se elimina por CASCADE.
    op.execute("DELETE FROM pantallas WHERE clave = 'recepcion'")
    _ordenar(ORDEN_ANTERIOR)
