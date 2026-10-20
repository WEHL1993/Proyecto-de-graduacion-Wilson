import { useState } from 'react'
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
  pedida: string | number | null
  recibida: string
  observacion: string
}

/** Cero documenta una falta; solo las cantidades positivas generan entradas. */
export const cantidadRecibidaValida = (v: string) =>
  /^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0 && Number(v) <= 9999999999.99

/** Formato canónico del UUID de autorización, sin validación fiscal. */
export const uuidAutorizacionValido = (v: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v.trim())

const FEL_VACIA = {
  serie: '', numero: '', numero_autorizacion: '', fecha_emision: '',
  condicion_pago: '', serie_admin: '', numero_admin: '',
}

export function ReceptionView() {
  const [params] = useSearchParams()
  const [pedidoId, setPedidoId] = useState(params.get('pedido') ?? '')
  const [factura, setFactura] = useState(FEL_VACIA)
  const [lineas, setLineas] = useState<LineaRecepcion[]>([])
  const [seleccion, setSeleccion] = useState('')
  const [aviso, setAviso] = useState('')
  const cache = useQueryClient()
  const pedidos = useQuery({ queryKey: ['recepcion-pedidos'], queryFn: pedidosPendientes })
  const productos = useQuery({ queryKey: ['recepcion-productos'], queryFn: productosRecepcion })
  const pedido = pedidos.data?.find((p) => p.id === pedidoId)
  // El detalle se deriva del pedido hasta la primera edición, sin sobrescribir lo capturado.
  const filas = lineas.length ? lineas : (pedido?.items.map((i) => ({
    producto_id: i.producto_id, nombre: `${i.sku} · ${i.producto_nombre}`,
    pedida: i.cantidad, recibida: String(i.cantidad), observacion: '',
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
  const cambiar = (indice: number, campo: 'recibida' | 'observacion', valor: string) =>
    setLineas(filas.map((f, i) => i === indice ? { ...f, [campo]: valor } : f))
  const valido = factura.serie.trim().length > 0 && /^[0-9]+$/.test(factura.numero.trim()) &&
    uuidAutorizacionValido(factura.numero_autorizacion) && !!factura.fecha_emision && filas.length > 0 &&
    filas.every((f) => cantidadRecibidaValida(f.recibida) && (pedidoId || Number(f.recibida) > 0)) &&
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
        numero_autorizacion: factura.numero_autorizacion.trim(), fecha_emision: factura.fecha_emision,
        condicion_pago: factura.condicion_pago.trim() || null,
        serie_admin: factura.serie_admin.trim() || null, numero_admin: factura.numero_admin.trim() || null,
        items: filas.map((f) => ({ producto_id: f.producto_id,
          cantidad_recibida: f.recibida, observacion: f.observacion.trim() })),
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
              ['numero_autorizacion', 'UUID de autorización', 36], ['fecha_emision', 'Fecha de emisión', 10],
              ['condicion_pago', 'Condición de pago (opcional)', 150],
              ['serie_admin', 'Serie admin (opcional)', 50], ['numero_admin', 'Número admin (opcional)', 50],
            ] as const).map(([campo, etiqueta, max]) => <Campo key={campo} etiqueta={etiqueta}>
              <input className={CLASE_INPUT} type={campo === 'fecha_emision' ? 'date' : 'text'}
                required={['serie', 'numero', 'numero_autorizacion', 'fecha_emision'].includes(campo)}
                maxLength={max} inputMode={campo === 'numero' ? 'numeric' : undefined}
                pattern={campo === 'numero' ? '[0-9]+' : undefined}
                value={factura[campo]} onChange={(e) => setFactura({ ...factura, [campo]: e.target.value })}
                aria-invalid={campo === 'numero_autorizacion' && !!factura[campo] && !uuidAutorizacionValido(factura[campo])}
                aria-describedby={campo === 'numero_autorizacion' ? 'ayuda-uuid-fel' : undefined} />
              {campo === 'numero_autorizacion' && <span id="ayuda-uuid-fel">
                {factura[campo] && !uuidAutorizacionValido(factura[campo])
                  ? 'Ingrese un UUID válido con formato XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX.'
                  : 'Ejemplo: 1FEF6CC7-4B72-4F43-A218-C10D0D12CE48'}
              </span>}
            </Campo>)}
          </div>
          {pedidoId && !pedidos.isPending && !pedido && <p role="alert">El pedido ya no está pendiente. Seleccione otro pedido.</p>}
        </Card>
        <Card titulo="Productos recibidos">
          {!pedidoId && <div className="mb-4 flex flex-wrap items-end gap-2">
            <Campo etiqueta="Producto">
              <select className={CLASE_INPUT} value={seleccion} onChange={(e) => setSeleccion(e.target.value)}>
                <option value="">Seleccione un producto</option>
                {productos.data?.filter((p) => !filas.some((f) => f.producto_id === p.id)).map((p) =>
                  <option key={p.id} value={p.id}>{p.sku} · {p.nombre}</option>)}
              </select>
            </Campo>
            <Button disabled={!seleccion || filas.length >= 200} onClick={() => {
              const p = productos.data?.find((v) => v.id === seleccion)
              if (p) setLineas([...filas, { producto_id: p.id, nombre: `${p.sku} · ${p.nombre}`,
                pedida: null, recibida: '', observacion: '' }])
              setSeleccion('')
            }}>Agregar producto</Button>
          </div>}
          {!filas.length ? <p className="text-sm text-muted">Seleccione un pedido o agregue los productos entregados.</p> :
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left">
                <th scope="col">Producto</th><th scope="col">Cantidad pedida</th>
                <th scope="col">Cantidad recibida</th><th scope="col">Observación</th>
                {!pedidoId && <th scope="col">Acciones</th>}
              </tr></thead>
              <tbody>{filas.map((f, i) => <tr key={f.producto_id} className="border-b border-line">
                <th scope="row" className="py-3 pr-3 text-left font-normal">{f.nombre}</th>
                <td className="num pr-3">{f.pedida ?? '—'}</td>
                <td className="p-2"><input aria-label={`Cantidad recibida de ${f.nombre}`} type="number"
                  min="0" max="9999999999.99" step="0.01" required className={`${CLASE_INPUT} w-36`}
                  value={f.recibida} onChange={(e) => cambiar(i, 'recibida', e.target.value)} /></td>
                <td className="p-2"><input aria-label={`Observación de ${f.nombre}`} maxLength={300}
                  className={CLASE_INPUT} value={f.observacion} onChange={(e) => cambiar(i, 'observacion', e.target.value)} /></td>
                {!pedidoId && <td><Button aria-label={`Quitar ${f.nombre}`}
                  onClick={() => setLineas(filas.filter((_, n) => n !== i))}>Quitar</Button></td>}
              </tr>)}</tbody>
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
