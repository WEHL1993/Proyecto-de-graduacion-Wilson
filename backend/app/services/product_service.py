"""CRUD administrativo de productos con baja lógica (ADR-16).

- Alta: crea el producto y su fila de `inventario` en 0 en la misma transacción.
- Edición: parcial; no toca existencias (eso es un ajuste con kardex) ni el estado.
- Baja: **lógica** (`activo = false`), nunca física: el producto está referenciado por ventas,
  cargas, kardex, pedidos y pronósticos. Se bloquea si tiene stock reservado o está en una carga
  vigente (`PRODUCTO_EN_USO`). Es idempotente.
"""

import uuid
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.models.catalog import Inventario, Producto
from app.repositories import product_repo
from app.schemas.products import ProductoCreate, ProductoOut, ProductoPage, ProductoUpdate
from app.services.bitacora_service import auditar

CERO = Decimal("0.00")


# ------------------------------------------------------------------ DTO
def _a_dto(producto: Producto, inv: Inventario | None, categoria: str) -> ProductoOut:
    actual = inv.stock_actual if inv else CERO
    reservado = inv.stock_reservado if inv else CERO
    return ProductoOut(
        id=producto.id,
        sku=producto.sku,
        nombre=producto.nombre,
        categoria_id=producto.categoria_id,
        categoria=categoria,
        proveedor_id=producto.proveedor_id,
        unidad_medida=producto.unidad_medida,
        precio_venta=producto.precio_venta,
        costo_unitario=producto.costo_unitario,
        stock_minimo=producto.stock_minimo,
        unidades_por_paquete=producto.unidades_por_paquete,
        medida_ml=producto.medida_ml,
        sabor=producto.sabor,
        activo=producto.activo,
        stock_actual=actual,
        stock_reservado=reservado,
        stock_disponible=actual - reservado,
        creado_en=producto.creado_en,
    )


def _dto(db: Session, producto: Producto) -> ProductoOut:
    inv = product_repo.existencia_de(db, producto.id)
    nombres = product_repo.nombre_de_categorias(db, {producto.categoria_id})
    return _a_dto(producto, inv, nombres.get(producto.categoria_id, ""))


# ------------------------------------------------------------------ validaciones
def _normalizar_sku(sku: str) -> str:
    limpio = sku.strip().upper()
    if not limpio:
        raise AppError("SKU_INVALIDO", "El SKU no puede estar vacío.")
    return limpio


def _limpiar_sabor(sabor: str | None) -> str | None:
    limpio = (sabor or "").strip()
    return limpio or None


def _obtener(db: Session, producto_id: uuid.UUID, *, bloquear: bool = False) -> Producto:
    producto = product_repo.obtener(db, producto_id, bloquear=bloquear)
    if producto is None:
        raise AppError("PRODUCTO_NO_ENCONTRADO", "El producto no existe.", status_code=404)
    return producto


def _sku_duplicado() -> AppError:
    return AppError("SKU_DUPLICADO", "Ya existe un producto con ese SKU.", status_code=409)


def _validar_categoria(db: Session, categoria_id: uuid.UUID) -> None:
    if not product_repo.categoria_existe(db, categoria_id):
        raise AppError(
            "CATEGORIA_NO_ENCONTRADA", "La categoría indicada no existe.", status_code=404
        )


def _validar_proveedor(db: Session, proveedor_id: uuid.UUID | None) -> None:
    if proveedor_id is not None and not product_repo.proveedor_existe(db, proveedor_id):
        raise AppError(
            "PROVEEDOR_NO_ENCONTRADO", "El proveedor indicado no existe.", status_code=404
        )


# ------------------------------------------------------------------ consulta
@auditar
def listar(
    db: Session,
    *,
    activo: bool | None,
    categoria_id: uuid.UUID | None,
    q: str | None,
    limit: int,
    offset: int,
) -> ProductoPage:
    filas, total = product_repo.listar(
        db, activo=activo, categoria_id=categoria_id, q=q, limit=limit, offset=offset
    )
    nombres = product_repo.nombre_de_categorias(db, {p.categoria_id for p, _ in filas})
    return ProductoPage(
        items=[_a_dto(p, inv, nombres.get(p.categoria_id, "")) for p, inv in filas],
        total=total,
        limit=limit,
        offset=offset,
    )


@auditar
def obtener(db: Session, producto_id: uuid.UUID) -> ProductoOut:
    return _dto(db, _obtener(db, producto_id))


# ------------------------------------------------------------------ escritura
@auditar
def crear(db: Session, datos: ProductoCreate, actor_id: uuid.UUID) -> ProductoOut:
    sku = _normalizar_sku(datos.sku)
    if product_repo.obtener_por_sku(db, sku) is not None:
        raise _sku_duplicado()
    _validar_categoria(db, datos.categoria_id)
    _validar_proveedor(db, datos.proveedor_id)

    campos = datos.model_dump()
    campos.update(sku=sku, nombre=datos.nombre.strip(), unidad_medida=datos.unidad_medida.strip())
    campos["sabor"] = _limpiar_sabor(datos.sabor)
    try:
        producto = product_repo.crear(db, campos)
        db.commit()
    except IntegrityError as exc:  # carrera con otra alta del mismo SKU
        db.rollback()
        raise _sku_duplicado() from exc
    return _dto(db, producto)


@auditar
def actualizar(
    db: Session, producto_id: uuid.UUID, datos: ProductoUpdate, actor_id: uuid.UUID
) -> ProductoOut:
    producto = _obtener(db, producto_id, bloquear=True)
    campos = datos.model_fields_set

    if datos.sku is not None:
        sku = _normalizar_sku(datos.sku)
        existente = product_repo.obtener_por_sku(db, sku)
        if existente is not None and existente.id != producto.id:
            raise _sku_duplicado()
        producto.sku = sku
    if datos.categoria_id is not None:
        _validar_categoria(db, datos.categoria_id)
        producto.categoria_id = datos.categoria_id
    if "proveedor_id" in campos:  # None explícito = quitar proveedor
        _validar_proveedor(db, datos.proveedor_id)
        producto.proveedor_id = datos.proveedor_id
    if datos.nombre is not None:
        producto.nombre = datos.nombre.strip()
    if datos.unidad_medida is not None:
        producto.unidad_medida = datos.unidad_medida.strip()
    if datos.precio_venta is not None:
        producto.precio_venta = datos.precio_venta
    if datos.costo_unitario is not None:
        producto.costo_unitario = datos.costo_unitario
    if datos.stock_minimo is not None:
        producto.stock_minimo = datos.stock_minimo
    if datos.unidades_por_paquete is not None:
        producto.unidades_por_paquete = datos.unidades_por_paquete
    if "medida_ml" in campos:  # None explícito = quitar la medida
        producto.medida_ml = datos.medida_ml
    if "sabor" in campos:
        producto.sabor = _limpiar_sabor(datos.sabor)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _sku_duplicado() from exc
    return _dto(db, producto)


@auditar
def dar_de_baja(db: Session, producto_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Baja lógica idempotente. 409 `PRODUCTO_EN_USO` si tiene reservas o cargas vigentes."""
    producto = _obtener(db, producto_id, bloquear=True)
    if not producto.activo:
        return

    # Se bloquea la existencia: una reserva concurrente espera a que termine la baja.
    inv = product_repo.existencia_de(db, producto.id, bloquear=True)
    reservado = inv.stock_reservado if inv else CERO
    cargas = product_repo.cargas_vigentes_con(db, producto.id)
    if reservado > 0 or cargas:
        raise AppError(
            "PRODUCTO_EN_USO",
            "No se puede dar de baja: el producto tiene stock reservado o está en cargas vigentes.",
            status_code=409,
            detalle={
                "stock_reservado": str(reservado),
                "cargas_vigentes": [str(c) for c in cargas],
            },
        )
    producto.activo = False
    db.commit()


@auditar
def reactivar(db: Session, producto_id: uuid.UUID, actor_id: uuid.UUID) -> ProductoOut:
    producto = _obtener(db, producto_id, bloquear=True)
    if not producto.activo:
        producto.activo = True
        db.commit()
    return _dto(db, producto)
