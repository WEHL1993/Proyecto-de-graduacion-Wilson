"""Unifica los nombres de rol con la tesis y asegura el rol Liquidador (M01).

Los `UPDATE` conservan los ids de `roles`, por lo que `usuarios_roles` y `roles_permisos`
siguen intactos. Idempotente: puede ejecutarse sobre una base ya renombrada o con el
rol Liquidador ya sembrado. El downgrade solo revierte los nombres; no borra Liquidador.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nombre anterior, nombre canónico)
RENOMBRES = (
    ('Admin', 'Administrador'),
    ('Inventario', 'EncargadoInventario'),
    ('Ventas', 'EncargadoVentas'),
    ('Bodega', 'EncargadoBodega'),
    ('Compras', 'EncargadoCompras'),
)

DESC_LIQUIDADOR_ANTERIOR = 'Registro, cierre y consulta de la liquidación diaria de ventas (ADR-14).'
DESC_LIQUIDADOR = (
    'Responsable de registrar y cerrar la liquidación diaria por ruta y vendedor (ADR-14).'
)

# Permisos del rol Liquidador (NO incluye `liquidaciones:corregir`, solo Administrador).
PERMISOS_LIQUIDADOR = (
    ('liquidaciones:registrar', 'Registro y edición de borradores de la liquidación diaria.'),
    ('liquidaciones:cerrar', 'Cierre de la liquidación diaria (alimenta el modelo).'),
    ('liquidaciones:leer', 'Consulta del historial de liquidaciones y su cuadre de caja.'),
)


def _renombrar(origen: str, destino: str) -> None:
    op.execute(
        f"UPDATE roles SET nombre = '{destino}' "
        f"WHERE nombre = '{origen}' "
        f"AND NOT EXISTS (SELECT 1 FROM roles WHERE nombre = '{destino}')"
    )


def upgrade() -> None:
    """Upgrade schema."""
    for anterior, canonico in RENOMBRES:
        _renombrar(anterior, canonico)

    op.execute(
        f"INSERT INTO roles (nombre, descripcion) VALUES ('Liquidador', '{DESC_LIQUIDADOR}') "
        "ON CONFLICT (nombre) DO NOTHING"
    )
    # Solo corrige la descripción si sigue siendo la sembrada originalmente.
    op.execute(
        f"UPDATE roles SET descripcion = '{DESC_LIQUIDADOR}' "
        f"WHERE nombre = 'Liquidador' AND descripcion = '{DESC_LIQUIDADOR_ANTERIOR}'"
    )
    for codigo, descripcion in PERMISOS_LIQUIDADOR:
        op.execute(
            f"INSERT INTO permisos (codigo, descripcion) VALUES ('{codigo}', '{descripcion}') "
            "ON CONFLICT (codigo) DO NOTHING"
        )
        op.execute(
            "INSERT INTO roles_permisos (rol_id, permiso_id) "
            f"SELECT r.id, p.id FROM roles r, permisos p "
            f"WHERE r.nombre = 'Liquidador' AND p.codigo = '{codigo}' "
            "ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    """Downgrade schema: solo revierte los nombres; el rol Liquidador y sus permisos se conservan."""
    for anterior, canonico in RENOMBRES:
        _renombrar(canonico, anterior)
