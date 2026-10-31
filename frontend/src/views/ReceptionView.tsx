import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../components/common/Button'
import { Campo, Card, CLASE_INPUT } from '../components/common/Card'
import { AlertBanner, Cargando } from '../components/feedback/feedback'
import { pedidosPendientes, productosRecepcion, registrarRecepcion } from '../services/purchasingApi'
import { mensajeError } from '../utils/errors'

export interface LineaRecepcion {
  producto_id: string
  nombre: string
  sku: string
  descripcion: string
  pedida: string | number | null
  recibida: string
  precio: string
  observacion: string
}

/** Precio de la factura: vacío (no se registra) o monto con hasta 4 decimales. */
export const precioUnitarioValido = (v: string) => v === '' || /^\d+(\.\d{1,4})?$/.test(v)

/** Importe de una línea: cantidad por precio, o nada si falta alguno de los dos. */
export const importeLinea = (recibida: string, precio: string): number | null =>
  cantidadRecibidaValida(recibida) && precio !== '' && precioUnitarioValido(precio)
    ? Math.round(Number(recibida) * Number(precio) * 100) / 100 : null

/** Producto cuyo código o nombre coincide exactamente (sin mayúsculas) con lo escrito. */
export function buscarProducto<T extends { id: string; sku: string; nombre: string }>(
  productos: readonly T[] | undefined, texto: string, excluidos: ReadonlySet<string> = new Set(),
): T | undefined {
  const t = texto.trim().toLowerCase()
  if (!t) return undefined
  return productos?.find((p) => !excluidos.has(p.id) &&
    (p.sku.toLowerCase() === t || p.nombre.toLowerCase() === t || `${p.sku} · ${p.nombre}`.toLowerCase() === t))
}

const quetzales = new Intl.NumberFormat('es-GT', { style: 'currency', currency: 'GTQ', currencyDisplay: 'narrowSymbol' })
const dinero = (v: number | null) => v === null ? '—' : quetzales.format(v)

/** Cero documenta una falta; solo las cantidades positivas generan entradas. */
export const cantidadRecibidaValida = (v: string) =>
  /^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0 && Number(v) <= 9999999999.99

const FEL_VACIA = {
  serie: '', numero: '', fecha_emision: '', condicion_pago: '',
}

export function ReceptionView() {
  const [params] = useSearchParams()
  const [pedidoId, setPedidoId] = useState(params.get('pedido') ?? '')
  const [factura, setFactura] = useState(FEL_VACIA)
  const [lineas, setLineas] = useState<LineaRecepcion[]>([])
  const [nuevo, setNuevo] = useState({ sku: '', descripcion: '' })
  const [enfocar, setEnfocar] = useState('')
  const [aviso, setAviso] = useState('')
  const cache = useQueryClient()
  const pedidos = useQuery({ queryKey: ['recepcion-pedidos'], queryFn: pedidosPendientes })
  const productos = useQuery({ queryKey: ['recepcion-productos'], queryFn: productosRecepcion })
  const pedido = pedidos.data?.find((p) => p.id === pedidoId)
  // El detalle se deriva del pedido hasta la primera edición, sin sobrescribir lo capturado.
  const filas = lineas.length ? lineas : (pedido?.items.map((i) => ({
    producto_id: i.producto_id, nombre: `${i.sku} · ${i.producto_nombre}`,
    sku: i.sku, descripcion: i.producto_nombre,
    pedida: i.cantidad, recibida: String(i.cantidad), precio: String(Number(i.costo_unitario)), observacion: '',
  })) ?? [])
  const guardar = useMutation({
    mutationFn: registrarRecepcion,
    onSuccess: (r) => {
      setAviso(r.estado_pedido === 'recibido_parcial'
        ? 'Recepción registrada con diferencias. Pedido recibido parcialmente.'
        : 'Recepción de mercadería registrada.')
      setPedidoId(''); setLineas([]); setFactura(FEL_VACIA)
      for (const key of ['recepcion-pedidos', 'compras-pedidos', 'compras-sugerencias', 'inventario-existencias', 'inventario-kardex'])
        void cache.invalidateQueries({ queryKey: [key] })
    },
  })
  useEffect(() => {
    if (enfocar) document.querySelector<HTMLInputElement>(`[data-cantidad="${enfocar}"]`)?.focus()
  }, [enfocar])
  /** Escribir un código o nombre existente agrega el producto como línea y deja lista una fila vacía. */
  const escribirNuevo = (campo: 'sku' | 'descripcion', valor: string) => {
    const p = filas.length < 200
      ? buscarProducto(productos.data, valor, new Set(filas.map((f) => f.producto_id))) : undefined
    if (!p) { setNuevo({ sku: '', descripcion: '', [campo]: valor }); return }
    setLineas([...filas, { producto_id: p.id, nombre: `${p.sku} · ${p.nombre}`,
      sku: p.sku, descripcion: p.nombre, pedida: null, recibida: '',
      precio: String(Number(p.costo_unitario)), observacion: '' }])
    setNuevo({ sku: '', descripcion: '' })
    setEnfocar(p.id)
  }
  const cambiar = (indice: number, campo: 'recibida' | 'precio' | 'observacion', valor: string) =>
    setLineas(filas.map((f, i) => i === indice ? { ...f, [campo]: valor } : f))
  const valido = factura.serie.trim().length > 0 && /^[0-9]+$/.test(factura.numero.trim()) &&
    !!factura.fecha_emision && filas.length > 0 &&
    filas.every((f) => cantidadRecibidaValida(f.recibida) && precioUnitarioValido(f.precio) && (pedidoId || Number(f.recibida) > 0)) &&
    filas.some((f) => Number(f.recibida) > 0) && (!pedidoId || !!pedido)
  return <div className="space-y-4">
    <h1 className="text-lg font-semibold">Recepción de mercadería</h1>
    <p className="text-sm text-muted">Registre la entrega física y la factura electrónica de la planta central.</p>
    {aviso && <AlertBanner tipo="exito">{aviso}</AlertBanner>}
    {(pedidos.isPending || productos.isPending) && <Cargando texto="Cargando pedidos y productos…" />}
    {(pedidos.isError || productos.isError) && <AlertBanner>{mensajeError(pedidos.error ?? productos.error)}
      <Button onClick={() => { void pedidos.refetch(); void productos.refetch() }}>Reintentar</Button>
    </AlertBanner>}
    <form onSubmit={(e) => {
      e.preventDefault()
      if (valido && !guardar.isPending) guardar.mutate({
        pedido_id: pedidoId || null,
        serie: factura.serie.trim().toUpperCase(), numero: factura.numero.trim(),
        fecha_emision: factura.fecha_emision,
        condicion_pago: factura.condicion_pago.trim() || null,
        items: filas.map((f) => ({ producto_id: f.producto_id,
          cantidad_recibida: f.recibida, precio_unitario: f.precio === '' ? null : f.precio,
          observacion: f.observacion.trim() })),
      })
    }}>
      <fieldset disabled={guardar.isPending || pedidos.isPending || productos.isPending} className="space-y-4">
        <Card titulo="Factura electrónica de planta central">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta="Pedido pendiente">
              <select className={CLASE_INPUT} value={pedidoId} onChange={(e) => {
                setPedidoId(e.target.value); setLineas([]); setAviso(''); guardar.reset()
              }}>
                <option value="">Sin pedido</option>
                {pedidos.data?.map((p) => <option key={p.id} value={p.id}>{p.id.slice(0, 8)} · {p.fecha_pedido}</option>)}
              </select>
            </Campo>
            {([
              ['serie', 'Serie FEL', 50], ['numero', 'Número FEL', 50],
              ['fecha_emision', 'Fecha de emisión', 10],
              ['condicion_pago', 'Condición de pago (opcional)', 150],
            ] as const).map(([campo, etiqueta, max]) => <Campo key={campo} etiqueta={etiqueta}>
              <input className={CLASE_INPUT} type={campo === 'fecha_emision' ? 'date' : 'text'}
                required={['serie', 'numero', 'fecha_emision'].includes(campo)}
                maxLength={max} inputMode={campo === 'numero' ? 'numeric' : undefined}
                pattern={campo === 'numero' ? '[0-9]+' : undefined}
                value={factura[campo]} onChange={(e) => setFactura({ ...factura, [campo]: e.target.value })} />
            </Campo>)}
          </div>
          {pedidoId && !pedidos.isPending && !pedido && <p role="alert">El pedido ya no está pendiente. Seleccione otro pedido.</p>}
        </Card>
        <Card titulo="Productos recibidos">
          {!pedidoId && <p className="mb-2 text-sm text-muted">Escriba el código o el nombre del producto en la fila vacía para agregarlo.</p>}
          {!pedidoId && <>
            <datalist id="lista-codigos">{productos.data?.map((p) => <option key={p.id} value={p.sku}>{p.nombre}</option>)}</datalist>
            <datalist id="lista-nombres">{productos.data?.map((p) => <option key={p.id} value={p.nombre}>{p.sku}</option>)}</datalist>
          </>}
          {(!pedidoId || filas.length > 0) &&
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left">
                <th scope="col">Código</th><th scope="col">Descripción</th>
                {pedidoId && <th scope="col">Cantidad pedida</th>}
                <th scope="col">Cantidad</th><th scope="col">Precio unitario</th>
                <th scope="col" className="text-right">Importe bruto</th>
                <th scope="col" className="text-right">Subtotal</th><th scope="col">Observación</th>
                {!pedidoId && <th scope="col">Acciones</th>}
              </tr></thead>
              <tbody>{filas.map((f, i) => <tr key={f.producto_id} className="border-b border-line">
                <th scope="row" className="py-3 pr-3 text-left font-normal">{f.sku}</th>
                <td className="pr-3">{f.descripcion}</td>
                {pedidoId && <td className="num pr-3">{f.pedida ?? '—'}</td>}
                <td className="p-2"><input aria-label={`Cantidad recibida de ${f.nombre}`} type="number"
                  data-cantidad={f.producto_id}
                  min="0" max="9999999999.99" step="0.01" required className={`${CLASE_INPUT} w-36`}
                  value={f.recibida} onChange={(e) => cambiar(i, 'recibida', e.target.value)} /></td>
                <td className="p-2"><input aria-label={`Precio unitario de ${f.nombre}`} inputMode="decimal"
                  maxLength={19} className={`${CLASE_INPUT} w-32`}
                  aria-invalid={!precioUnitarioValido(f.precio)}
                  value={f.precio} onChange={(e) => cambiar(i, 'precio', e.target.value)} /></td>
                <td className="num pr-3 text-right">{dinero(importeLinea(f.recibida, f.precio))}</td>
                <td className="num pr-3 text-right">{dinero(importeLinea(f.recibida, f.precio))}</td>
                <td className="p-2"><input aria-label={`Observación de ${f.nombre}`} maxLength={300}
                  className={CLASE_INPUT} value={f.observacion} onChange={(e) => cambiar(i, 'observacion', e.target.value)} /></td>
                {!pedidoId && <td><Button aria-label={`Quitar ${f.nombre}`}
                  onClick={() => setLineas(filas.filter((_, n) => n !== i))}>Quitar</Button></td>}
              </tr>)}
              {!pedidoId && filas.length < 200 && <tr className="border-b border-line">
                <td className="p-2"><input aria-label="Código del producto" list="lista-codigos" autoComplete="off"
                  className={`${CLASE_INPUT} w-32`} value={nuevo.sku}
                  onChange={(e) => escribirNuevo('sku', e.target.value)} /></td>
                <td className="p-2"><input aria-label="Descripción del producto" list="lista-nombres" autoComplete="off"
                  className={CLASE_INPUT} value={nuevo.descripcion}
                  onChange={(e) => escribirNuevo('descripcion', e.target.value)} /></td>
                <td colSpan={6} />
              </tr>}</tbody>
              <tfoot><tr>
                <th scope="row" colSpan={pedidoId ? 6 : 5} className="py-3 text-right font-semibold">Total</th>
                <td className="num text-right font-semibold">
                  {dinero(filas.reduce((t, f) => t + (importeLinea(f.recibida, f.precio) ?? 0), 0))}</td>
                <td colSpan={pedidoId ? 1 : 2} />
              </tr></tfoot>
            </table></div>}
          {pedido && filas.some((f) => Number(f.recibida) !== Number(f.pedida)) &&
            <p className="mt-3 text-sm text-muted">Hay diferencias. El pedido quedará recibido parcialmente.</p>}
        </Card>
        {guardar.isError && <AlertBanner>{mensajeError(guardar.error)}</AlertBanner>}
        <Button type="submit" variant="primary" disabled={!valido || guardar.isPending}>
          {guardar.isPending ? 'Registrando recepción…' : 'Guardar recepción'}
        </Button>
      </fieldset>
    </form>
  </div>
}
