import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MetricPoint } from '../../types'
import { fmt } from '../../utils/format'

const BRAND = 'rgb(var(--brand))'
const BAD = 'rgb(var(--bad))'
const MUTED = 'rgb(var(--muted))'
const GRID = 'rgb(var(--line))'

/** Evolución del MAPE por periodo frente al umbral (wireframe 2b). */
export function MapeTrendChart({ serie, umbral }: { serie: MetricPoint[]; umbral: number }) {
  const [tabla, setTabla] = useState(false)
  const datos = serie.map((p) => ({
    periodo: p.periodo_hasta,
    mape: p.mape ?? null,
    supera: p.supera_umbral,
  }))
  const maximo = Math.max(umbral * 1.3, ...datos.map((d) => d.mape ?? 0))

  if (!serie.length) {
    return <p className="py-8 text-center text-sm text-muted">Aún no hay periodos evaluados en este rango.</p>
  }

  return (
    <div>
      <div className="mb-1 flex justify-end">
        <button type="button" onClick={() => setTabla((v) => !v)} className="text-xs text-brand underline">
          {tabla ? 'Ver gráfica' : 'Ver como tabla'}
        </button>
      </div>
      {tabla ? (
        <table className="w-full text-sm">
          <caption className="sr-only">MAPE por periodo</caption>
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="py-1">Periodo</th>
              <th className="py-1 text-right">MAPE</th>
              <th className="py-1 text-right">Umbral</th>
              <th className="py-1 text-right">Estado</th>
            </tr>
          </thead>
          <tbody>
            {serie.map((p) => (
              <tr key={p.periodo_hasta} className="border-t border-line">
                <td className="py-1">
                  {p.periodo_desde} → {p.periodo_hasta}
                </td>
                <td className="num py-1 text-right">{fmt(p.mape, ' %')}</td>
                <td className="num py-1 text-right">{fmt(umbral, ' %')}</td>
                <td className="py-1 text-right">{p.supera_umbral ? '🔴 sobre umbral' : '🟢 dentro'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div role="img" aria-label={`Evolución del MAPE. Último valor ${fmt(serie.at(-1)?.mape, ' %')}, umbral ${fmt(umbral, ' %')}.`}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={datos} margin={{ top: 12, right: 56, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="periodo" tick={{ fill: MUTED, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis
                domain={[0, Math.ceil(maximo)]}
                tick={{ fill: MUTED, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={36}
                unit="%"
              />
              <Tooltip
                formatter={(v) => [fmt(v as number, ' %'), 'MAPE']}
                labelFormatter={(l) => `Periodo al ${l}`}
                contentStyle={{ background: 'rgb(var(--panel))', border: `1px solid ${GRID}`, borderRadius: 6, fontSize: 12 }}
              />
              <ReferenceLine
                y={umbral}
                stroke={BAD}
                strokeDasharray="6 4"
                label={{ value: `umbral ${fmt(umbral)}`, position: 'right', fill: BAD, fontSize: 11 }}
              />
              <Line
                type="monotone"
                dataKey="mape"
                stroke={BRAND}
                strokeWidth={2}
                dot={{ r: 4, stroke: 'rgb(var(--panel))', strokeWidth: 2, fill: BRAND }}
                activeDot={{ r: 6 }}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
