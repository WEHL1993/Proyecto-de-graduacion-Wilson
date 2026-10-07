import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { useCategorias, useProductoActions, useProductos, useProveedores } from '../hooks/useProducts'
import { usePermissions } from '../hooks/usePermissions'
import type { ProductoCreate, ProductoOut, ProductoUpdate, TipoAjuste } from '../types'
import { apiError, mensajeError } from '../utils/errors'
import { fmt } from '../utils/format'

const POR_PAGINA = 25

// ---------------------------------------------------------------- formulario de producto
export interface FormProducto {
  sku: string
  nombre: string
  categoria_id: string
  proveedor_id: string
  unidad_medida: string
  precio_venta: string
  costo_unitario: string
  stock_minimo: string
  /** Presentación en paquete (M02): unidades por paquete, medida en ml (opcional) y sabor (opcional). */
  unidades_por_paquete: string
  medida_ml: string
  sabor: string
}

export const FORM_PRODUCTO_VACIO: FormProducto = {
  sku: '',
  nombre: '',
  categoria_id: '',
  proveedor_id: '',
  unidad_medida: 'unidad',
  precio_venta: '0',
  costo_unitario: '0',
  stock_minimo: '0',
  unidades_por_paquete: '1',
  medida_ml: '',
  sabor: '',
}

export const formDesdeProducto = (p: ProductoOut): FormProducto => ({
  sku: p.sku,
  nombre: p.nombre,
  categoria_id: p.categoria_id,
  proveedor_id: p.proveedor_id ?? '',
  unidad_medida: p.unidad_medida,
  precio_venta: String(p.precio_venta),
  costo_unitario: String(p.costo_unitario),
  stock_minimo: String(p.stock_minimo),
  unidades_por_paquete: String(p.unidades_por_paquete),
  medida_ml: p.medida_ml == null ? '' : String(p.medida_ml),
  sabor: p.sabor ?? '',
})

/** Presentación legible: «6 × 3030 ml · COLA»; sin medida en ml solo se muestran las unidades. */
export function presentacion(p: Pick<ProductoOut, 'unidades_por_paquete' | 'medida_ml' | 'sabor'>): string {
  const medida = p.medida_ml == null ? '' : ` × ${p.medida_ml} ml`
  const sabor = p.sabor ? ` · ${p.sabor}` : ''
  return `${p.unidades_por_paquete}${medida}${sabor}`
}

const esEnteroPositivo = (v: string) => /^\d+$/.test(v.trim()) && Number(v) >= 1

const esNoNegativo = (v: string) => v.trim() !== '' && Number.isFinite(Number(v)) && Number(v) >= 0

/** Errores por campo; vacío = válido. Refleja las reglas del backend (`ProductoCreate`). */
export function validarProducto(f: FormProducto): Partial<Record<keyof FormProducto, string>> {
  const e: Partial<Record<keyof FormProducto, string>> = {}
  if (!f.sku.trim()) e.sku = 'El SKU es obligatorio.'
  else if (f.sku.trim().length > 30) e.sku = 'Máximo 30 caracteres.'
  if (f.nombre.trim().length < 2) e.nombre = 'Mínimo 2 caracteres.'
  if (!f.categoria_id) e.categoria_id = 'Seleccione una categoría.'
  if (!f.unidad_medida.trim()) e.unidad_medida = 'Indique la unidad de medida.'
  if (!esNoNegativo(f.precio_venta)) e.precio_venta = 'Debe ser un número ≥ 0.'
  if (!esNoNegativo(f.costo_unitario)) e.costo_unitario = 'Debe ser un número ≥ 0.'
  if (!esNoNegativo(f.stock_minimo)) e.stock_minimo = 'Debe ser un número ≥ 0.'
  if (!esEnteroPositivo(f.unidades_por_paquete)) e.unidades_por_paquete = 'Entero ≥ 1.'
  if (f.medida_ml.trim() !== '' && !esEnteroPositivo(f.medida_ml)) e.medida_ml = 'Entero ≥ 1 o vacío.'
  if (f.sabor.trim().length > 60) e.sabor = 'Máximo 60 caracteres.'
  return e
}

const aCreate = (f: FormProducto): ProductoCreate => ({
  sku: f.sku.trim(),
  nombre: f.nombre.trim(),
  categoria_id: f.categoria_id,
  proveedor_id: f.proveedor_id || null,
  unidad_medida: f.unidad_medida.trim(),
  precio_venta: f.precio_venta.trim(),
  costo_unitario: f.costo_unitario.trim(),
  stock_minimo: f.stock_minimo.trim(),
  unidades_por_paquete: Number(f.unidades_por_paquete),
  medida_ml: f.medida_ml.trim() === '' ? null : Number(f.medida_ml),
  sabor: f.sabor.trim() || null,
})

const aUpdate = (f: FormProducto): ProductoUpdate => aCreate(f)

// ---------------------------------------------------------------- formulario de ajuste
export interface FormAjuste {
  tipo: TipoAjuste
  cantidad: string
  motivo: string
}

export const FORM_AJUSTE_VACIO: FormAjuste = { tipo: 'incremento', cantidad: '', motivo: '' }

const ETIQUETA_AJUSTE: Record<TipoAjuste, string> = {
  incremento: 'Incremento (sumar)',
  decremento: 'Decremento (restar)',
  fijar: 'Fijar (conteo físico)',
}

/** Stock físico que quedaría tras el ajuste; `null` si la cantidad no es un número válido. */
export function stockResultante(tipo: TipoAjuste, cantidad: string, actual: number): number | null {
  if (cantidad.trim() === '' || !Number.isFinite(Number(cantidad))) return null
  const q = Number(cantidad)
  if (tipo === 'fijar') return q
  return tipo === 'incremento' ? actual + q : actual - q
}

/** Errores del ajuste, con las mismas reglas que el backend (no deja el stock bajo lo reservado). */
export function validarAjuste(
  f: FormAjuste,
  producto: Pick<ProductoOut, 'stock_actual' | 'stock_reservado'>,
): Partial<Record<keyof FormAjuste, string>> {
  const e: Partial<Record<keyof FormAjuste, string>> = {}
  const actual = Number(producto.stock_actual)
  const reservado = Number(producto.stock_reservado)
  const q = Number(f.cantidad)
  const resultante = stockResultante(f.tipo, f.cantidad, actual)
  if (resultante === null) e.cantidad = 'Ingrese una cantidad numérica.'
  else if (q < 0) e.cantidad = 'La cantidad no puede ser negativa.'
  else if (f.tipo !== 'fijar' && q === 0) e.cantidad = 'La cantidad debe ser mayor que 0.'
  else if (resultante < reservado)
    e.cantidad = `El stock no puede quedar por debajo de lo reservado (${fmt(reservado)}).`
  else if (resultante === actual) e.cantidad = 'El ajuste no modifica el stock actual.'
  if (f.motivo.trim().length < 5) e.motivo = 'Describa el motivo (mínimo 5 caracteres).'
  else if (f.motivo.trim().length > 300) e.motivo = 'Máximo 300 caracteres.'
  return e
}

/** Mensaje del servidor, con el detalle útil de `PRODUCTO_EN_USO` y `STOCK_INSUFICIENTE`. */
export function textoError(e: unknown): string {
  const api = apiError(e)
  const base = mensajeError(e)
  const d = api?.detalle as Record<string, unknown> | undefined
  if (!api || !d) return base
  if (api.codigo === 'PRODUCTO_EN_USO') {
    const cargas = Array.isArray(d.cargas_vigentes) ? d.cargas_vigentes.length : 0
    return `${base} (reservado: ${fmt(String(d.stock_reservado ?? 0))}; cargas vigentes: ${cargas}).`
  }
  if (api.codigo === 'STOCK_INSUFICIENTE' && d.stock_actual !== undefined)
    return `${base} (actual: ${fmt(String(d.stock_actual))}; reservado: ${fmt(String(d.stock_reservado))}).`
  return base
}

// ---------------------------------------------------------------- modales
function ModalProducto({ producto, onCerrar }: { producto: ProductoOut | null; onCerrar: () => void }) {
  const edicion = producto !== null
  const [form, setForm] = useState<FormProducto>(producto ? formDesdeProducto(producto) : FORM_PRODUCTO_VACIO)
  const [intento, setIntento] = useState(false)
  const categorias = useCategorias()
  const proveedores = useProveedores()
  const { crear, actualizar } = useProductoActions()
  const mutacion = edicion ? actualizar : crear
  const errores = validarProducto(form)
  const set = <K extends keyof FormProducto>(k: K, v: FormProducto[K]) => setForm((f) => ({ ...f, [k]: v }))

  const enviar = (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    if (Object.keys(errores).length) return
    const alTerminar = { onSuccess: onCerrar }
    if (producto) actualizar.mutate({ id: producto.id, datos: aUpdate(form) }, alTerminar)
    else crear.mutate(aCreate(form), alTerminar)
  }
  const mostrar = (k: keyof FormProducto) =>
    intento && errores[k] ? (
      <span role="alert" className="text-xs font-normal text-bad">
        {errores[k]}
      </span>
    ) : null

  return (
    <Modal
      titulo={edicion ? 'Editar producto' : 'Nuevo producto'}
      onCerrar={onCerrar}
      acciones={
        <>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button variant="primary" type="submit" form="form-producto" disabled={mutacion.isPending}>
            {mutacion.isPending ? 'Guardando…' : edicion ? 'Guardar cambios' : 'Crear producto'}
          </Button>
        </>
      }
    >
      <form id="form-producto" onSubmit={enviar} noValidate className="flex flex-col gap-3">
        {mutacion.isError && <AlertBanner>{textoError(mutacion.error)}</AlertBanner>}
        <div className="grid grid-cols-2 gap-3">
          <Campo etiqueta="SKU">
            <input value={form.sku} onChange={(e) => set('sku', e.target.value)} className={CLASE_INPUT} maxLength={30} />
            {mostrar('sku')}
          </Campo>
          <Campo etiqueta="Unidad de medida">
            <input value={form.unidad_medida} onChange={(e) => set('unidad_medida', e.target.value)} className={CLASE_INPUT} />
            {mostrar('unidad_medida')}
          </Campo>
        </div>
        <Campo etiqueta="Nombre">
          <input value={form.nombre} onChange={(e) => set('nombre', e.target.value)} className={CLASE_INPUT} />
          {mostrar('nombre')}
        </Campo>
        <Campo etiqueta="Categoría">
          <select value={form.categoria_id} onChange={(e) => set('categoria_id', e.target.value)} className={CLASE_INPUT}>
            <option value="">Seleccione…</option>
            {categorias.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
          {mostrar('categoria_id')}
        </Campo>
        <Campo etiqueta="Proveedor (opcional)">
          <select value={form.proveedor_id} onChange={(e) => set('proveedor_id', e.target.value)} className={CLASE_INPUT}>
            <option value="">Sin proveedor</option>
            {proveedores.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <div className="grid grid-cols-3 gap-3">
          <Campo etiqueta="Precio de venta">
            <input inputMode="decimal" value={form.precio_venta} onChange={(e) => set('precio_venta', e.target.value)} className={CLASE_INPUT} />
            {mostrar('precio_venta')}
          </Campo>
          <Campo etiqueta="Costo unitario">
            <input inputMode="decimal" value={form.costo_unitario} onChange={(e) => set('costo_unitario', e.target.value)} className={CLASE_INPUT} />
            {mostrar('costo_unitario')}
          </Campo>
          <Campo etiqueta="Stock mínimo">
            <input inputMode="decimal" value={form.stock_minimo} onChange={(e) => set('stock_minimo', e.target.value)} className={CLASE_INPUT} />
            {mostrar('stock_minimo')}
          </Campo>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Campo etiqueta="Unidades por paquete">
            <input inputMode="numeric" value={form.unidades_por_paquete} onChange={(e) => set('unidades_por_paquete', e.target.value)} className={CLASE_INPUT} />
            {mostrar('unidades_por_paquete')}
          </Campo>
          <Campo etiqueta="Medida (ml, opcional)">
            <input inputMode="numeric" value={form.medida_ml} onChange={(e) => set('medida_ml', e.target.value)} className={CLASE_INPUT} />
            {mostrar('medida_ml')}
          </Campo>
          <Campo etiqueta="Sabor (opcional)">
            <input value={form.sabor} onChange={(e) => set('sabor', e.target.value)} className={CLASE_INPUT} maxLength={60} />
            {mostrar('sabor')}
          </Campo>
        </div>
        {edicion && (
          <p className="text-xs text-muted">
            Las existencias no se editan aquí: use «Ajustar stock» para dejar un movimiento en el kardex.
          </p>
        )}
      </form>
    </Modal>
  )
}

function ModalAjuste({ producto, onCerrar }: { producto: ProductoOut; onCerrar: () => void }) {
  const [form, setForm] = useState<FormAjuste>(FORM_AJUSTE_VACIO)
  const [intento, setIntento] = useState(false)
  const { ajustar } = useProductoActions()
  const errores = validarAjuste(form, producto)
  const actual = Number(producto.stock_actual)
  const resultante = stockResultante(form.tipo, form.cantidad, actual)
  const set = <K extends keyof FormAjuste>(k: K, v: FormAjuste[K]) => setForm((f) => ({ ...f, [k]: v }))

  const enviar = (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    if (Object.keys(errores).length) return
    ajustar.mutate(
      { producto_id: producto.id, tipo: form.tipo, cantidad: form.cantidad.trim(), motivo: form.motivo.trim() },
      { onSuccess: onCerrar },
    )
  }
  const mostrar = (k: keyof FormAjuste) =>
    intento && errores[k] ? (
      <span role="alert" className="text-xs font-normal text-bad">
        {errores[k]}
      </span>
    ) : null

  return (
    <Modal
      titulo={`Ajustar stock · ${producto.sku}`}
      onCerrar={onCerrar}
      acciones={
        <>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button variant="primary" type="submit" form="form-ajuste" disabled={ajustar.isPending}>
            {ajustar.isPending ? 'Aplicando…' : 'Aplicar ajuste'}
          </Button>
        </>
      }
    >
      <form id="form-ajuste" onSubmit={enviar} noValidate className="flex flex-col gap-3">
        {ajustar.isError && <AlertBanner>{textoError(ajustar.error)}</AlertBanner>}
        <p>
          <span className="font-medium">{producto.nombre}</span>
          <span className="num block text-xs text-muted">
            Actual {fmt(producto.stock_actual)} · Reservado {fmt(producto.stock_reservado)} · Disponible{' '}
            {fmt(producto.stock_disponible)}
          </span>
        </p>
        <Campo etiqueta="Tipo de ajuste">
          <select value={form.tipo} onChange={(e) => set('tipo', e.target.value as TipoAjuste)} className={CLASE_INPUT}>
            {(Object.keys(ETIQUETA_AJUSTE) as TipoAjuste[]).map((t) => (
              <option key={t} value={t}>
                {ETIQUETA_AJUSTE[t]}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta={form.tipo === 'fijar' ? 'Stock físico contado' : 'Cantidad'}>
          <input inputMode="decimal" value={form.cantidad} onChange={(e) => set('cantidad', e.target.value)} className={CLASE_INPUT} />
          {mostrar('cantidad')}
        </Campo>
        <Campo etiqueta="Motivo">
          <textarea
            value={form.motivo}
            onChange={(e) => set('motivo', e.target.value)}
            className={CLASE_INPUT}
            rows={2}
            maxLength={300}
            placeholder="Ej.: conteo físico, merma, corrección de ingreso"
          />
          {mostrar('motivo')}
        </Campo>
        <p className="num text-sm" aria-live="polite">
          Stock resultante: <strong>{resultante === null ? '—' : fmt(resultante)}</strong>
        </p>
      </form>
    </Modal>
  )
}

function ModalBaja({ producto, onCerrar }: { producto: ProductoOut; onCerrar: () => void }) {
  const { darDeBaja } = useProductoActions()
  return (
    <Modal
      titulo="Dar de baja producto"
      onCerrar={onCerrar}
      acciones={
        <>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button variant="danger" disabled={darDeBaja.isPending} onClick={() => darDeBaja.mutate(producto.id, { onSuccess: onCerrar })}>
            {darDeBaja.isPending ? 'Procesando…' : 'Dar de baja'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {darDeBaja.isError && <AlertBanner>{textoError(darDeBaja.error)}</AlertBanner>}
        <p>
          ¿Dar de baja <strong>{producto.nombre}</strong> <span className="font-mono text-xs">({producto.sku})</span>?
        </p>
        <p className="text-xs text-muted">
          Es una baja lógica: el producto deja de usarse en cargas, pronósticos y alertas, pero su historial y kardex se conservan y
          puede reactivarse después.
        </p>
      </div>
    </Modal>
  )
}

type Modalidad =
  | { tipo: 'producto'; producto: ProductoOut | null }
  | { tipo: 'ajuste'; producto: ProductoOut }
  | { tipo: 'baja'; producto: ProductoOut }

// ---------------------------------------------------------------- vista
/** Catálogo de productos: alta, edición, baja lógica / reactivación y ajuste de stock (ADR-16). */
export function ProductsView() {
  const { can } = usePermissions()
  const puedeCrear = can('productos:crear')
  const puedeEditar = can('productos:editar')
  const puedeEliminar = can('productos:eliminar')
  const puedeAjustar = can('inventario:ajustar')

  const [q, setQ] = useState('')
  const [estado, setEstado] = useState<'activos' | 'bajas'>('activos')
  const [categoriaId, setCategoriaId] = useState('')
  const [pagina, setPagina] = useState(0)
  const [modal, setModal] = useState<Modalidad | null>(null)

  const categorias = useCategorias()
  const productos = useProductos({
    q: q.trim(),
    activo: estado === 'activos',
    categoriaId,
    limit: POR_PAGINA,
    offset: pagina * POR_PAGINA,
  })
  const { reactivar } = useProductoActions()
  const total = productos.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA))
  const filtrar = <T,>(fijar: (v: T) => void) => (v: T) => {
    fijar(v)
    setPagina(0)
  }
  const cerrar = () => setModal(null)

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Productos</h1>
          <p className="text-sm text-muted">Catálogo, baja lógica y ajuste manual de existencias.</p>
        </div>
        {puedeCrear && (
          <Button variant="primary" onClick={() => setModal({ tipo: 'producto', producto: null })}>
            + Nuevo producto
          </Button>
        )}
      </header>

      <Card>
        <div className="mb-3 flex flex-wrap gap-3">
          <Campo etiqueta="Buscar">
            <input
              value={q}
              onChange={(e) => filtrar(setQ)(e.target.value)}
              placeholder="SKU o nombre"
              className={`${CLASE_INPUT} w-56`}
            />
          </Campo>
          <Campo etiqueta="Categoría">
            <select value={categoriaId} onChange={(e) => filtrar(setCategoriaId)(e.target.value)} className={CLASE_INPUT}>
              <option value="">Todas</option>
              {categorias.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo etiqueta="Estado">
            <select
              value={estado}
              onChange={(e) => filtrar(setEstado)(e.target.value as typeof estado)}
              className={CLASE_INPUT}
            >
              <option value="activos">Activos</option>
              <option value="bajas">Dados de baja</option>
            </select>
          </Campo>
        </div>

        {reactivar.isError && <AlertBanner>{textoError(reactivar.error)}</AlertBanner>}
        {productos.isPending && <Cargando texto="Cargando productos…" />}
        {productos.isError && <AlertBanner>{mensajeError(productos.error)}</AlertBanner>}
        {productos.data && productos.data.items.length === 0 && (
          <EmptyState
            titulo={estado === 'activos' ? 'Sin productos' : 'Sin productos dados de baja'}
            detalle="Ningún producto coincide con los filtros aplicados."
          />
        )}
        {!!productos.data?.items.length && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-sm">
                <caption className="sr-only">Catálogo de productos</caption>
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-2 pr-3">Producto</th>
                    <th className="py-2 pr-3">Categoría</th>
                    <th className="py-2 pr-3">Presentación</th>
                    <th className="py-2 pr-3 text-right">Precio</th>
                    <th className="py-2 pr-3 text-right">Stock</th>
                    <th className="py-2 pr-3 text-right">Disponible</th>
                    <th className="py-2 pr-3 text-right">Mínimo</th>
                    <th className="py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {productos.data.items.map((p) => {
                    const bajo = Number(p.stock_disponible) < Number(p.stock_minimo)
                    return (
                      <tr key={p.id} className="border-b border-line align-top last:border-0">
                        <td className="py-2 pr-3">
                          {p.nombre} <span className="font-mono text-xs text-muted">{p.sku}</span>
                          {!p.activo && (
                            <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-muted">Baja</span>
                          )}
                        </td>
                        <td className="py-2 pr-3 text-xs">{p.categoria}</td>
                        <td className="num py-2 pr-3 text-xs">{presentacion(p)}</td>
                        <td className="num py-2 pr-3 text-right">{fmt(p.precio_venta)}</td>
                        <td className="num py-2 pr-3 text-right">{fmt(p.stock_actual)}</td>
                        <td className={`num py-2 pr-3 text-right font-medium ${p.activo && bajo ? 'text-bad' : ''}`}>
                          {fmt(p.stock_disponible)}
                        </td>
                        <td className="num py-2 pr-3 text-right">{fmt(p.stock_minimo)}</td>
                        <td className="py-2 text-right">
                          <div className="flex flex-wrap justify-end gap-1.5">
                            {puedeEditar && (
                              <Button onClick={() => setModal({ tipo: 'producto', producto: p })} aria-label={`Editar ${p.sku}`}>
                                Editar
                              </Button>
                            )}
                            {puedeAjustar && p.activo && (
                              <Button onClick={() => setModal({ tipo: 'ajuste', producto: p })} aria-label={`Ajustar stock de ${p.sku}`}>
                                Ajustar stock
                              </Button>
                            )}
                            {puedeEliminar && p.activo && (
                              <Button variant="danger" onClick={() => setModal({ tipo: 'baja', producto: p })} aria-label={`Dar de baja ${p.sku}`}>
                                Dar de baja
                              </Button>
                            )}
                            {puedeEliminar && !p.activo && (
                              <Button
                                disabled={reactivar.isPending && reactivar.variables === p.id}
                                onClick={() => reactivar.mutate(p.id)}
                                aria-label={`Reactivar ${p.sku}`}
                              >
                                Reactivar
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="num text-muted">
                {total} productos · página {pagina + 1} de {paginas}
              </span>
              <div className="flex gap-2">
                <Button disabled={pagina === 0} onClick={() => setPagina((n) => n - 1)}>
                  Anterior
                </Button>
                <Button disabled={pagina + 1 >= paginas} onClick={() => setPagina((n) => n + 1)}>
                  Siguiente
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      {modal?.tipo === 'producto' && (
        <ModalProducto key={modal.producto?.id ?? 'nuevo'} producto={modal.producto} onCerrar={cerrar} />
      )}
      {modal?.tipo === 'ajuste' && <ModalAjuste key={modal.producto.id} producto={modal.producto} onCerrar={cerrar} />}
      {modal?.tipo === 'baja' && <ModalBaja key={modal.producto.id} producto={modal.producto} onCerrar={cerrar} />}
    </div>
  )
}
