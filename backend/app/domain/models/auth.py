"""Autenticación y RBAC: usuarios, roles, permisos y tablas puente."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ColorRol, sql_in
from app.domain.models.base import AuditoriaMixin, Base, UUIDPkMixin


class Usuario(UUIDPkMixin, AuditoriaMixin, Base):
    __tablename__ = "usuarios"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nombre_completo: Mapped[str] = mapped_column(String(150))
    # Solo para usuarios con rol Proveedor (aislamiento por fila, TC-RBAC-03).
    proveedor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proveedores.id", ondelete="SET NULL"), index=True
    )
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())
    # Contraseña temporal: la fijó un administrador y el usuario debe cambiarla al ingresar.
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, server_default="false")
    ultimo_login: Mapped[datetime | None]

    roles: Mapped[list["Rol"]] = relationship(secondary="usuarios_roles", back_populates="usuarios")


class Rol(Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint(sql_in("color", ColorRol), name="color_valido"),)

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    # Un rol inactivo no otorga permisos ni se puede asignar (se conserva por historial).
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())
    # Rol protegido: sus permisos no se editan ni se desactiva (Administrador).
    es_sistema: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Los usuarios con este rol deben asociarse a un proveedor (aislamiento por fila).
    requiere_proveedor: Mapped[bool] = mapped_column(Boolean, server_default="false")
    color: Mapped[str] = mapped_column(String(20), server_default=ColorRol.NEUTRO.value)
    pantalla_inicio_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("pantallas.id", ondelete="SET NULL")
    )

    usuarios: Mapped[list[Usuario]] = relationship(
        secondary="usuarios_roles", back_populates="roles"
    )
    permisos: Mapped[list["Permiso"]] = relationship(
        secondary="roles_permisos", back_populates="roles"
    )


class Permiso(Base):
    __tablename__ = "permisos"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    # Formato `recurso:accion` (p. ej. `carga_ruta:aprobar`, `ml:metricas:leer`).
    codigo: Mapped[str] = mapped_column(String(60), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    # Agrupa la matriz de permisos por módulo (p. ej. `inventario`, `liquidaciones`).
    modulo: Mapped[str] = mapped_column(String(40), server_default="general")
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())

    roles: Mapped[list[Rol]] = relationship(secondary="roles_permisos", back_populates="permisos")


class RolPermiso(Base):
    __tablename__ = "roles_permisos"

    rol_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permiso_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("permisos.id", ondelete="CASCADE"), primary_key=True
    )


class UsuarioRol(Base):
    __tablename__ = "usuarios_roles"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    rol_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    asignado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class Pantalla(Base):
    """Pantalla del menú. Se muestra al usuario si tiene ALGUNO de sus permisos (`canAny`)."""

    __tablename__ = "pantallas"
    __table_args__ = (CheckConstraint("ruta LIKE '/%'", name="ruta_absoluta"),)

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    clave: Mapped[str] = mapped_column(String(40), unique=True)
    etiqueta: Mapped[str] = mapped_column(String(80))
    ruta: Mapped[str] = mapped_column(String(120))
    # Si se informa, la entrada del menú queda activa en todas las rutas bajo este prefijo.
    ruta_prefijo: Mapped[str | None] = mapped_column(String(120))
    grupo: Mapped[str] = mapped_column(String(40), server_default="General")
    orden: Mapped[int] = mapped_column(SmallInteger, server_default="100")
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())

    permisos: Mapped[list[Permiso]] = relationship(secondary="pantallas_permisos")


class PantallaPermiso(Base):
    __tablename__ = "pantallas_permisos"

    pantalla_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("pantallas.id", ondelete="CASCADE"), primary_key=True
    )
    permiso_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("permisos.id", ondelete="CASCADE"), primary_key=True
    )
