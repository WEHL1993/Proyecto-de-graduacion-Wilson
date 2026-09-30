import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { useComisiones, useRotacion, useVentasVsProyeccion } from '../hooks/useReports'
import { listarRutas } from '../services/catalogApi'
import { descargarConsolidado } from '../services/reportsApi'
import type { FiltroReportes, FormatoExport } from '../services/reportsApi'
import type { ComisionVendedor } from '../types'
import { mensajeError } from '../utils/errors'
import { fmt } from '../utils/format'

const BRAND = 'rgb(var(--brand))'
const PROYECTADO = 'rgb(var(--warn))'
const GOOD = 'rgb(var(--good))'
const MUTED = 'rgb(var(--muted))'
const GRID = 'rgb(var(--line))'
const TOOLTIP = { background: 'rgb(var(--panel))', border: `1px solid ${GRID}`, borderRadius: 6, fontSize: 12 }
const EJE = { fill: MUTED, fontSize: 11 }

/** Suma las liquidaciones de un vendedor a lo largo de los periodos consultados. */
export function comisionesPorAgente(filas: ComisionVendedor[]) {
  const porAgente = new Map<string, { vendedor: string; comision: number; vendido: number }>()
  for (const f of filas) {
    const acum = porAgente.get(f.vendedor_id) ?? { vendedor: f.vendedor, comision: 0, vendido: 0 }
    acum.comision += Number(f.comision_total)
    acum.vendido += Number(f.monto_vendido)
    porAgente.set(f.vendedor_id, acum)
  }
  return [...porAgente.values()].sort((a, b) => b.comision - a.comision)
}

const moneda = (v: number | string | null | undefined) => (v == null ? 's/d' : `Q ${fmt(v)}`)

function Kpi({ etiqueta, valor, detalle }: { etiqueta: string; valor: string; detalle?: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <p className="text-xs text-muted">{etiqueta}</p>
      <p className="num mt-1 text-xl font-semibold">{valor}</p>
      {detalle && <p className="mt-0.5 text-xs text-muted">{detalle}</p>}
    </div>
  )
}

function Estado({ q, vacio }: { q: { isLoading: boolean; isError: boolean; error: unknown }; vacio?: boolean }) {
  if (q.isLoading) return <Cargando />
  if (q.isError) return <AlertBanner>{mensajeError(q.error)}</AlertBanner>
  if (vacio) return <EmptyState titulo="Sin datos" detalle="No hay información para el periodo y la ruta seleccionados." />
  return null
}

export function ReportsView() {
  const [borrador, setBorrador] = useState<FiltroReportes>({})
  const [filtro, setFiltro] = useState<FiltroReportes>({})
  const [descarga, setDescarga] = useState<{ cargando: FormatoExport | null; error: string | null }>({ cargando: null, error: null })

  const rutas = useQuery({ queryKey: ['rutas'], queryFn: listarRutas })
  const ventas = useVentasVsProyeccion(filtro)
  const rotacion = useRotacion(filtro)
  const comisiones = useComisiones(filtro)

  const aplicar = () => setFiltro({ ...borrador })
  const rangoInvalido = Boolean(borrador.desde && borrador.hasta && borrador.desde > borrador.hasta)

  const exportar = async (formato: FormatoExport) => {
    setDescarga({ cargando: formato, error: null })
    try {
      await descargarConsolidado(filtro, formato)
      setDescarga({ cargando: null, error: null })
    } catch (e) {
      setDescarga({ cargando: null, error: mensajeError(e) })
    }
  }

  const datosRutas = (ventas.data?.rutas ?? []).map((r) => ({
    ruta: r.ruta_codigo,
    Real: Number(r.real),
    Proyectada: Number(r.proyectada),
  }))
  const datosDias = (ventas.data?.serie ?? []).map((d) => ({ fecha: d.fecha.slice(5), Real: Number(d.real), Proyectada: Number(d.proyectada) }))
  const agentes = comisionesPorAgente(comisiones.data?.liquidaciones ?? [])
  const desv = ventas.data && Number(ventas.data.total_proyectado) > 0
    ? ((Number(ventas.data.total_real) - Number(ventas.data.total_proyectado)) * 100) / Number(ventas.data.total_proyectado)
    : null

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Reportes gerenciales</h1>
          <p className="text-sm text-muted">
            Venta real vs. proyectada, rotación de inventario, quiebres por ruta y comisiones.
            {ventas.data && (
              <>
                {' '}
                Periodo: <span className="num">{ventas.data.desde}</span> → <span className="num">{ventas.data.hasta}</span>.
              </>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => exportar('xlsx')} disabled={descarga.cargando !== null}>
            {descarga.cargando === 'xlsx' ? 'Generando…' : '⬇ Excel (consolidado)'}
          </Button>
          <Button onClick={() => exportar('csv')} disabled={descarga.cargando !== null}>
            {descarga.cargando === 'csv' ? 'Generando…' : '⬇ CSV'}
          </Button>
        </div>
      </header>

      {descarga.error && <AlertBanner>No se pudo descargar el informe: {descarga.error}</AlertBanner>}

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Campo etiqueta="Desde">
            <input type="date" value={borrador.desde ?? ''} onChange={(e) => setBorrador((b) => ({ ...b, desde: e.target.value || undefined }))} className={CLASE_INPUT} />
          </Campo>
          <Campo etiqueta="Hasta">
            <input type="date" value={borrador.hasta ?? ''} onChange={(e) => setBorrador((b) => ({ ...b, hasta: e.target.value || undefined }))} className={CLASE_INPUT} />
          </Campo>
          <Campo etiqueta="Ruta">
            <select value={borrador.rutaId ?? ''} onChange={(e) => setBorrador((b) => ({ ...b, rutaId: e.target.value || undefined }))} className={CLASE_INPUT}>
              <option value="">Todas las rutas</option>
              {rutas.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.codigo} · {r.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Button variant="primary" onClick={aplicar} disabled={rangoInvalido}>
            Aplicar
          </Button>
          {rangoInvalido && <span role="alert" className="text-xs text-bad">«Desde» no puede ser posterior a «Hasta».</span>}
        </div>
        <p className="mt-2 text-xs text-muted">Sin fechas: últimos 30 días hasta el último dato disponible. Las comisiones se liquidan por mes.</p>
      </Card>

      <section aria-label="Indicadores" className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi etiqueta="Venta real (uds)" valor={fmt(ventas.data?.total_real)} />
        <Kpi etiqueta="Proyectada (uds)" valor={fmt(ventas.data?.total_proyectado)} detalle={desv == null ? undefined : `Desviación ${fmt(desv, ' %')}`} />
        <Kpi etiqueta="Rotación de inventario" valor={fmt(rotacion.data?.rotacion_global, '×')} detalle={rotacion.data?.dias_inventario ? `${fmt(rotacion.data.dias_inventario)} días de inventario` : undefined} />
        <Kpi etiqueta="Índice de quiebre" valor={fmt(rotacion.data?.indice_quiebre_global, ' %')} detalle="Líneas de carga limitadas por stock" />
        <Kpi etiqueta="Comisiones" valor={moneda(comisiones.data?.total_comisiones)} detalle={comisiones.data ? `${comisiones.data.periodo_desde} → ${comisiones.data.periodo_hasta}` : undefined} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Venta real vs. proyectada por ruta (unidades)">
          <Estado q={ventas} vacio={ventas.isSuccess && !datosRutas.length} />
          {!!datosRutas.length && (
            <div role="img" aria-label={`Barras de venta real y proyectada para ${datosRutas.length} rutas. Detalle en la tabla inferior.`}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={datosRutas} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="ruta" tick={EJE} tickLine={false} axisLine={{ stroke: GRID }} />
                  <YAxis tick={EJE} tickLine={false} axisLine={false} width={44} />
                  <Tooltip contentStyle={TOOLTIP} formatter={(v) => fmt(v as number)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Real" fill={BRAND} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="Proyectada" fill={PROYECTADO} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card titulo="Evolución diaria: real vs. proyectada (unidades)">
          <Estado q={ventas} vacio={ventas.isSuccess && !datosDias.length} />
          {!!datosDias.length && (
            <div role="img" aria-label="Líneas de venta diaria real y proyectada.">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={datosDias} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="fecha" tick={EJE} tickLine={false} axisLine={{ stroke: GRID }} />
                  <YAxis tick={EJE} tickLine={false} axisLine={false} width={44} />
                  <Tooltip contentStyle={TOOLTIP} formatter={(v) => fmt(v as number)} labelFormatter={(l) => `Día ${l}`} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="Real" stroke={BRAND} strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="Proyectada" stroke={PROYECTADO} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <Card titulo="Comisiones por agente">
        <Estado q={comisiones} vacio={comisiones.isSuccess && !agentes.length} />
        {!!agentes.length && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div role="img" aria-label="Barras horizontales de comisión total por agente.">
              <ResponsiveContainer width="100%" height={Math.max(160, agentes.length * 36 + 40)}>
                <BarChart data={agentes} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={EJE} tickLine={false} axisLine={{ stroke: GRID }} />
                  <YAxis type="category" dataKey="vendedor" tick={EJE} tickLine={false} axisLine={false} width={110} />
                  <Tooltip contentStyle={TOOLTIP} formatter={(v) => moneda(v as number)} />
                  <Bar dataKey="comision" name="Comisión" fill={GOOD} radius={[0, 3, 3, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Liquidación de comisiones por vendedor y periodo</caption>
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th className="py-1.5 pr-3">Periodo</th>
                    <th className="py-1.5 pr-3">Vendedor</th>
                    <th className="py-1.5 pr-3 text-right">Vendido</th>
                    <th className="py-1.5 pr-3 text-right">Comisión</th>
                    <th className="py-1.5 text-right">%</th>
                  </tr>
                </thead>
                <tbody>
                  {comisiones.data?.liquidaciones.map((l) => (
                    <tr key={`${l.vendedor_id}-${l.periodo}`} className="border-t border-line">
                      <td className="num py-1.5 pr-3">{l.periodo}</td>
                      <td className="py-1.5 pr-3">{l.vendedor}</td>
                      <td className="num py-1.5 pr-3 text-right">{moneda(l.monto_vendido)}</td>
                      <td className="num py-1.5 pr-3 text-right font-medium">{moneda(l.comision_total)}</td>
                      <td className="num py-1.5 text-right">{fmt(l.porcentaje_efectivo, ' %')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      <Card titulo="Rotación de inventario e índice de quiebres por ruta">
        <Estado q={rotacion} vacio={rotacion.isSuccess && !rotacion.data?.rutas.length} />
        {!!rotacion.data?.rutas.length && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Rotación y quiebres por ruta</caption>
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="py-1.5 pr-3">Ruta</th>
                  <th className="py-1.5 pr-3 text-right">Uds. vendidas</th>
                  <th className="py-1.5 pr-3 text-right">Costo de ventas</th>
                  <th className="py-1.5 pr-3 text-right">Rotación</th>
                  <th className="py-1.5 pr-3 text-right">Líneas ajustadas</th>
                  <th className="py-1.5 pr-3 text-right">Índice de quiebre</th>
                  <th className="py-1.5 text-right">Uds. no cubiertas</th>
                </tr>
              </thead>
              <tbody>
                {rotacion.data.rutas.map((r) => (
                  <tr key={r.ruta_id} className="border-t border-line">
                    <td className="py-1.5 pr-3">
                      <span className="font-medium">{r.ruta_codigo}</span> <span className="text-muted">{r.ruta_nombre}</span>
                    </td>
                    <td className="num py-1.5 pr-3 text-right">{fmt(r.unidades_vendidas)}</td>
                    <td className="num py-1.5 pr-3 text-right">{moneda(r.costo_ventas)}</td>
                    <td className="num py-1.5 pr-3 text-right">{fmt(r.rotacion, '×')}</td>
                    <td className="num py-1.5 pr-3 text-right">
                      {r.lineas_ajustadas} / {r.lineas_carga}
                    </td>
                    <td className={`num py-1.5 pr-3 text-right ${Number(r.indice_quiebre) >= 30 ? 'font-semibold text-bad' : ''}`}>{fmt(r.indice_quiebre, ' %')}</td>
                    <td className="num py-1.5 text-right">{fmt(r.unidades_no_cubiertas)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">
              Rotación = costo de ventas del periodo / valor del inventario actual ({moneda(rotacion.data.valor_inventario)}). Índice de quiebre = % de líneas de carga limitadas por el stock disponible.
            </p>
          </div>
        )}
      </Card>
    </div>
  )
}
