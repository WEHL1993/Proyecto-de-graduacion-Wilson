"""Autenticación y RBAC: usuarios, roles, permisos y tablas puente."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Identity, SmallInteger, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    ultimo_login: Mapped[datetime | None]

    roles: Mapped[list["Rol"]] = relationship(secondary="usuarios_roles", back_populates="usuarios")


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))

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
