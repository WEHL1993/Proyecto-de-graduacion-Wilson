import { useState } from 'react'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { useExistencias, useKardex } from '../hooks/useInventory'
import type { StockItem, TipoMovimiento } from '../types'
import { mensajeError } from '../utils/errors'
import { fmt } from '../utils/format'

const TIPOS: TipoMovimiento[] = ['entrada', 'salida', 'ajuste', 'reserva', 'liberacion']
const POR_PAGINA = 25

const ETIQUETA_TIPO: Record<TipoMovimiento, { texto: string; clase: string }> = {
  entrada: { texto: '▲ Entrada', clase: 'text-good' },
  salida: { texto: '▼ Salida', clase: 'text-bad' },
  ajuste: { texto: '≈ Ajuste', clase: 'text-warn' },
  reserva: { texto: '◐ Reserva', clase: 'text-muted' },
  liberacion: { texto: '◑ Liberación', clase: 'text-muted' },
}

/** Productos con disponible por debajo del mínimo, del más crítico al menos (mayor déficit primero). */
export const alertasStockBajo = (items: StockItem[]): StockItem[] =>
  items
    .filter((i) => i.bajo_minimo)
    .sort((a, b) => Number(a.stock_disponible) - Number(a.stock_minimo) - (Number(b.stock_disponible) - Number(b.stock_minimo)))

/** Consulta de existencias, alertas de stock bajo y visor cronológico del kardex. */
export function InventoryView() {
  const existencias = useExistencias()
  const items = existencias.data?.items ?? []
  const bajos = alertasStockBajo([...items])

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Inventario y Kardex</h1>
      {existencias.isPending && <Cargando texto="Cargando existencias…" />}
      {existencias.isError && <AlertBanner>{mensajeError(existencias.error)}</AlertBanner>}

      {existencias.data && (
        <>
          <Card titulo={`Alertas de stock bajo (${bajos.length})`}>
            {bajos.length === 0 ? (
              <p className="text-sm text-muted">Todos los productos están sobre su stock mínimo.</p>
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {bajos.map((i) => {
                  const sinStock = Number(i.stock_disponible) <= 0
                  return (
                    <li
                      key={i.producto_id}
                      className={`rounded-md border px-3 py-2 text-sm ${sinStock ? 'border-bad' : 'border-warn'}`}
                    >
                      <p className={`text-xs font-semibold uppercase ${sinStock ? 'text-bad' : 'text-warn'}`}>
                        {sinStock ? 'Sin disponible' : 'Bajo el mínimo'}
                      </p>
                      <p>
                        {i.nombre} <span className="font-mono text-xs text-muted">{i.sku}</span>
                      </p>
                      <p className="num text-xs text-muted">
                        Disponible {fmt(i.stock_disponible)} · Mínimo {fmt(i.stock_minimo)}
                      </p>
                    </li>
                  )
                })}
              </ul>
            )}
          </Card>

          <Card titulo="Existencias">
            {items.length === 0 ? (
              <EmptyState titulo="Sin productos" detalle="No hay productos activos en el catálogo." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-muted">
                      <th className="py-2">Producto</th>
                      <th className="py-2 text-right">Stock actual</th>
                      <th className="py-2 text-right">Reservado</th>
                      <th className="py-2 text-right">Disponible</th>
                      <th className="py-2 text-right">Mínimo</th>
                      <th className="py-2 pl-4">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((i) => (
                      <tr key={i.producto_id} className="border-b border-line last:border-0">
                        <td className="py-2">
                          {i.nombre} <span className="font-mono text-xs text-muted">{i.sku}</span>
                        </td>
                        <td className="num py-2 text-right">{fmt(i.stock_actual)}</td>
                        <td className="num py-2 text-right">{fmt(i.stock_reservado)}</td>
                        <td className="num py-2 text-right font-medium">{fmt(i.stock_disponible)}</td>
                        <td className="num py-2 text-right">{fmt(i.stock_minimo)}</td>
                        <td className={`py-2 pl-4 text-xs font-semibold ${i.bajo_minimo ? 'text-bad' : 'text-good'}`}>
                          {i.bajo_minimo ? '⚠ Stock bajo' : '✔ Suficiente'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <VisorKardex productos={items} />
        </>
      )}
    </div>
  )
}

function VisorKardex({ productos }: { productos: StockItem[] }) {
  const [productoId, setProductoId] = useState('')
  const [tipo, setTipo] = useState<TipoMovimiento | ''>('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [pagina, setPagina] = useState(0)
  const kardex = useKardex({
    productoId,
    tipo: tipo || undefined,
    desde,
    hasta,
    limit: POR_PAGINA,
    offset: pagina * POR_PAGINA,
  })
  const nombres = new Map(productos.map((p) => [p.producto_id, p]))
  const rangoInvalido = Boolean(desde && hasta && desde > hasta)
  const total = kardex.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA))
  const filtrar = <T,>(fijar: (v: T) => void) => (v: T) => {
    fijar(v)
    setPagina(0)
  }

  return (
    <Card titulo="Movimientos de kardex">
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Campo etiqueta="Producto">
          <select
            className={CLASE_INPUT}
            value={productoId}
            onChange={(e) => filtrar(setProductoId)(e.target.value)}
          >
            <option value="">Todos</option>
            {productos.map((p) => (
              <option key={p.producto_id} value={p.producto_id}>
                {p.sku} · {p.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Tipo">
          <select
            className={CLASE_INPUT}
            value={tipo}
            onChange={(e) => filtrar(setTipo)(e.target.value as TipoMovimiento | '')}
          >
            <option value="">Todos</option>
            {TIPOS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Desde">
          <input type="date" className={CLASE_INPUT} value={desde} onChange={(e) => filtrar(setDesde)(e.target.value)} />
        </Campo>
        <Campo etiqueta="Hasta">
          <input type="date" className={CLASE_INPUT} value={hasta} onChange={(e) => filtrar(setHasta)(e.target.value)} />
        </Campo>
        {(productoId || tipo || desde || hasta) && (
          <Button
            onClick={() => {
              setProductoId('')
              setTipo('')
              setDesde('')
              setHasta('')
              setPagina(0)
            }}
          >
            Limpiar filtros
          </Button>
        )}
      </div>

      {rangoInvalido && <AlertBanner>La fecha «Desde» no puede ser posterior a «Hasta».</AlertBanner>}
      {kardex.isPending && <Cargando texto="Cargando movimientos…" />}
      {kardex.isError && <AlertBanner>{mensajeError(kardex.error)}</AlertBanner>}
      {kardex.data && kardex.data.items.length === 0 && (
        <EmptyState titulo="Sin movimientos" detalle="No hay movimientos de kardex con estos filtros." />
      )}
      {kardex.data && kardex.data.items.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-2">Fecha</th>
                  <th className="py-2">Producto</th>
                  <th className="py-2">Movimiento</th>
                  <th className="py-2 text-right">Cantidad</th>
                  <th className="py-2 text-right">Saldo</th>
                  <th className="py-2 pl-4">Referencia</th>
                </tr>
              </thead>
              <tbody>
                {kardex.data.items.map((m) => {
                  const etiqueta = ETIQUETA_TIPO[m.tipo_movimiento]
                  const producto = nombres.get(m.producto_id)
                  return (
                    <tr key={m.id} className="border-b border-line last:border-0">
                      <td className="num whitespace-nowrap py-2">
                        {new Date(m.fecha_movimiento).toLocaleString('es-GT', { dateStyle: 'short', timeStyle: 'short' })}
                      </td>
                      <td className="py-2">
                        {producto?.nombre ?? m.producto_id.slice(0, 8)}{' '}
                        <span className="font-mono text-xs text-muted">{producto?.sku}</span>
                      </td>
                      <td className={`py-2 text-xs font-semibold ${etiqueta.clase}`}>{etiqueta.texto}</td>
                      <td className="num py-2 text-right">{fmt(m.cantidad)}</td>
                      <td className="num py-2 text-right">{fmt(m.saldo_resultante)}</td>
                      <td className="py-2 pl-4 text-xs text-muted">
                        {m.referencia_tipo ?? '—'}
                        {m.referencia_id && <span className="font-mono"> {m.referencia_id.slice(0, 8)}</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="num text-muted">
              {total} movimientos · página {pagina + 1} de {paginas}
            </span>
            <div className="flex gap-2">
              <Button disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </Button>
              <Button disabled={pagina + 1 >= paginas} onClick={() => setPagina((p) => p + 1)}>
                Siguiente
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  )
}
