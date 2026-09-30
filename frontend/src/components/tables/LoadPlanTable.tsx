import type { LoadPlanItem } from '../../types'
import { fmt } from '../../utils/format'

export type Cantidades = Record<string, string>

export type EstadoStock = 'sin_existencia' | 'limitado' | 'ok'

/** ⛔ sin existencia · ⚠ limitado por stock (demanda > sugerido) · sin marca en otro caso. */
export function estadoStock(item: LoadPlanItem): EstadoStock {
  if (Number(item.stock_disponible) <= 0) return 'sin_existencia'
  return item.ajustado_por_stock ? 'limitado' : 'ok'
}

/** Cantidad aprobada válida: número ≥ 0 y nunca mayor al stock disponible (regla 2a). */
export function errorCantidad(texto: string, stockDisponible: number | string): string | null {
  if (texto.trim() === '') return 'Ingrese una cantidad.'
  const n = Number(texto)
  if (!Number.isFinite(n) || n < 0) return 'Debe ser un número mayor o igual a 0.'
  if (n > Number(stockDisponible)) return `No puede exceder el stock disponible (${fmt(stockDisponible)}).`
  return null
}

interface Props {
  items: LoadPlanItem[]
  editable: boolean
  seleccion: Set<string>
  cantidades: Cantidades
  onSeleccion: (productoId: string, marcado: boolean) => void
  onSeleccionTodos: (marcado: boolean) => void
  onCantidad: (productoId: string, valor: string) => void
}

export function LoadPlanTable({
  items,
  editable,
  seleccion,
  cantidades,
  onSeleccion,
  onSeleccionTodos,
  onCantidad,
}: Props) {
  const todos = items.length > 0 && items.every((i) => seleccion.has(i.producto_id))
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="w-8 py-2">
              <input
                type="checkbox"
                aria-label="Seleccionar todas las filas"
                checked={todos}
                disabled={!editable}
                onChange={(e) => onSeleccionTodos(e.target.checked)}
              />
            </th>
            <th className="py-2">SKU</th>
            <th className="py-2">Producto</th>
            <th className="py-2 text-right">Demanda predicha</th>
            <th className="py-2 text-right">Stock disponible</th>
            <th className="py-2 text-right">Sugerido</th>
            <th className="py-2 text-right">Aprobado {editable && '(edit)'}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const id = item.producto_id
            const estado = estadoStock(item)
            const texto = cantidades[id] ?? ''
            const error = editable && seleccion.has(id) ? errorCantidad(texto, item.stock_disponible) : null
            const tooltip = `Demanda original: ${fmt(item.cantidad_predicha)} · Cantidad ajustada: ${fmt(item.cantidad_sugerida)}`
            return (
              <tr key={id} className="border-b border-line last:border-0">
                <td className="py-2">
                  <input
                    type="checkbox"
                    aria-label={`Incluir ${item.sku}`}
                    checked={seleccion.has(id)}
                    disabled={!editable}
                    onChange={(e) => onSeleccion(id, e.target.checked)}
                  />
                </td>
                <td className="py-2 font-mono text-xs">{item.sku}</td>
                <td className="py-2">{item.producto_nombre ?? '—'}</td>
                <td className="num py-2 text-right">{fmt(item.cantidad_predicha)}</td>
                <td className="num py-2 text-right">
                  {fmt(item.stock_disponible)}
                  {estado === 'sin_existencia' && (
                    <span title="Sin existencia (ver alerta de compras)" aria-label="Sin existencia" className="ml-1">
                      ⛔
                    </span>
                  )}
                </td>
                <td className="num py-2 text-right">
                  {fmt(item.cantidad_sugerida)}
                  {estado === 'limitado' && (
                    <span title={tooltip} aria-label={`Limitado por stock. ${tooltip}`} className="ml-1 text-warn">
                      ⚠
                    </span>
                  )}
                  {estado === 'sin_existencia' && (
                    <span title={tooltip} className="sr-only">
                      {tooltip}
                    </span>
                  )}
                </td>
                <td className="py-2 text-right">
                  {editable ? (
                    <>
                      <input
                        type="number"
                        inputMode="decimal"
                        min={0}
                        max={Number(item.stock_disponible)}
                        step="0.01"
                        aria-label={`Cantidad aprobada de ${item.sku}`}
                        aria-invalid={error !== null}
                        value={texto}
                        onChange={(e) => onCantidad(id, e.target.value)}
                        className={`num w-24 rounded-md border bg-panel px-2 py-1 text-right ${error ? 'border-bad' : 'border-line'}`}
                      />
                      {error && <p className="mt-0.5 max-w-[14rem] text-xs text-bad">{error}</p>}
                    </>
                  ) : (
                    <span className="num">{item.cantidad_aprobada != null ? fmt(item.cantidad_aprobada) : '—'}</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
