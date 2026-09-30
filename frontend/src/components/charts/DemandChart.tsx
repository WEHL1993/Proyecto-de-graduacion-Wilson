import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fmt } from '../../utils/format'

export interface PuntoDemanda {
  fecha: string
  predicha: number
  inferior?: number | null
  superior?: number | null
}

const BRAND = 'rgb(var(--brand))'
const MUTED = 'rgb(var(--muted))'
const GRID = 'rgb(var(--line))'

/** Demanda predicha con banda al 95 % (wireframe 2a). */
export function DemandChart({ puntos }: { puntos: PuntoDemanda[] }) {
  if (!puntos.length) {
    return <p className="py-8 text-center text-sm text-muted">Sin pronóstico para mostrar.</p>
  }
  const datos = puntos.map((p) => ({
    fecha: p.fecha.slice(5),
    predicha: p.predicha,
    banda: p.inferior != null && p.superior != null ? [p.inferior, p.superior] : null,
  }))
  return (
    <div role="img" aria-label={`Demanda predicha para ${puntos.length} día(s)`}>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={datos} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="fecha" tick={{ fill: MUTED, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={{ fill: MUTED, fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
          <Tooltip
            formatter={(v, nombre) => [
              Array.isArray(v) ? `${fmt(v[0])} – ${fmt(v[1])}` : fmt(v as number, ' u'),
              nombre === 'banda' ? 'Banda 95 %' : 'Predicha',
            ]}
            contentStyle={{ background: 'rgb(var(--panel))', border: `1px solid ${GRID}`, borderRadius: 6, fontSize: 12 }}
          />
          <Area dataKey="banda" stroke="none" fill={BRAND} fillOpacity={0.15} isAnimationActive={false} />
          <Line
            dataKey="predicha"
            stroke={BRAND}
            strokeWidth={2}
            dot={{ r: 3.5, stroke: 'rgb(var(--panel))', strokeWidth: 2, fill: BRAND }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 text-xs text-muted">Línea: demanda predicha · Sombreado: banda al 95 %.</p>
    </div>
  )
}
