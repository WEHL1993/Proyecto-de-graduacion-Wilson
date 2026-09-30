"""Registro de todos los modelos ORM.

Importar este paquete garantiza que `Base.metadata` contenga todas las tablas
(requerido por Alembic autogenerate).
"""

from app.domain.models.auth import Permiso, Rol, RolPermiso, Usuario, UsuarioRol
from app.domain.models.base import Base
from app.domain.models.catalog import Categoria, Inventario, Kardex, Producto, Proveedor, Ruta
from app.domain.models.ml import (
    Alerta,
    JobML,
    MetricaEvaluacion,
    ModeloML,
    ParametroSistema,
    PronosticoDemanda,
)
from app.domain.models.operations import CargaRuta, DetalleCarga, DetallePedido, PedidoProveedor
from app.domain.models.sales import Comision, EtlLote, VentaHistorica

__all__ = [
    "Base",
    # Auth / RBAC
    "Usuario",
    "Rol",
    "Permiso",
    "RolPermiso",
    "UsuarioRol",
    # Catálogos y stock
    "Categoria",
    "Proveedor",
    "Producto",
    "Ruta",
    "Inventario",
    "Kardex",
    # Operación comercial
    "CargaRuta",
    "DetalleCarga",
    "PedidoProveedor",
    "DetallePedido",
    # Histórico / ETL
    "EtlLote",
    "VentaHistorica",
    "Comision",
    # ML y pronósticos
    "ModeloML",
    "MetricaEvaluacion",
    "PronosticoDemanda",
    "Alerta",
    "ParametroSistema",
    "JobML",
]
