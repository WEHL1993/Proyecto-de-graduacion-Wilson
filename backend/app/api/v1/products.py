"""CRUD de productos con baja lógica (`/products`). Sin reglas de negocio: delega en
`product_service`. Lectura con `inventario:leer`; escritura con `productos:*` (ADR-16)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.products import ProductoCreate, ProductoOut, ProductoPage, ProductoUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Products"])

PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("inventario:leer"))]
PuedeCrear = Annotated[UsuarioAutenticado, Depends(require_permission("productos:crear"))]
PuedeEditar = Annotated[UsuarioAutenticado, Depends(require_permission("productos:editar"))]
PuedeEliminar = Annotated[UsuarioAutenticado, Depends(require_permission("productos:eliminar"))]


@router.get(
    "",
    response_model=ProductoPage,
    summary="Listar productos",
    description=(
        "Requiere `inventario:leer`. Por defecto solo activos (`activo=true`); `activo=false` "
        "lista las bajas. Filtros: `categoria_id` y `q` (SKU o nombre)."
    ),
)
def listar_productos(
    db: DBSession,
    _usuario: PuedeLeer,
    activo: bool | None = True,
    categoria_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductoPage:
    return product_service.listar(
        db, activo=activo, categoria_id=categoria_id, q=q, limit=limit, offset=offset
    )


@router.get(
    "/{producto_id}",
    response_model=ProductoOut,
    summary="Detalle de un producto",
    description="Requiere `inventario:leer`. 404 `PRODUCTO_NO_ENCONTRADO`.",
)
def obtener_producto(db: DBSession, _usuario: PuedeLeer, producto_id: UUID) -> ProductoOut:
    return product_service.obtener(db, producto_id)


@router.post(
    "",
    response_model=ProductoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear producto",
    description=(
        "Requiere `productos:crear`. Crea también su existencia en 0. 409 `SKU_DUPLICADO`; "
        "404 `CATEGORIA_NO_ENCONTRADA` / `PROVEEDOR_NO_ENCONTRADO`."
    ),
)
def crear_producto(db: DBSession, actor: PuedeCrear, datos: ProductoCreate) -> ProductoOut:
    return product_service.crear(db, datos, actor.id)


@router.patch(
    "/{producto_id}",
    response_model=ProductoOut,
    summary="Actualizar producto (parcial)",
    description=(
        "Requiere `productos:editar`. No modifica existencias ni estado. 404 "
        "`PRODUCTO_NO_ENCONTRADO`; 409 `SKU_DUPLICADO`."
    ),
)
def actualizar_producto(
    db: DBSession, actor: PuedeEditar, producto_id: UUID, datos: ProductoUpdate
) -> ProductoOut:
    return product_service.actualizar(db, producto_id, datos, actor.id)


@router.delete(
    "/{producto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja un producto (baja lógica)",
    description=(
        "Requiere `productos:eliminar`. Marca `activo=false`; el historial se conserva. "
        "Idempotente. 409 `PRODUCTO_EN_USO` si tiene stock reservado o cargas vigentes."
    ),
)
def eliminar_producto(db: DBSession, actor: PuedeEliminar, producto_id: UUID) -> Response:
    product_service.dar_de_baja(db, producto_id, actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{producto_id}/reactivate",
    response_model=ProductoOut,
    summary="Reactivar un producto dado de baja",
    description="Requiere `productos:eliminar`. Idempotente. 404 `PRODUCTO_NO_ENCONTRADO`.",
)
def reactivar_producto(db: DBSession, actor: PuedeEliminar, producto_id: UUID) -> ProductoOut:
    return product_service.reactivar(db, producto_id, actor.id)
