import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../app/providers/AuthProvider'
import { DemandChart } from '../components/charts/DemandChart'
import type { PuntoDemanda } from '../components/charts/DemandChart'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { LoadPlanTable, errorCantidad } from '../components/tables/LoadPlanTable'
import type { Cantidades } from '../components/tables/LoadPlanTable'
import { useDemandForecast } from '../hooks/useDemandForecast'
import { useLoadPlan, useLoadPlanActions } from '../hooks/useLoadPlan'
import { useModelMetrics } from '../hooks/useModelMetrics'
import { listarRutas } from '../services/catalogApi'
import type { LoadPlanRequest, LoadPlanResponse } from '../types'
import { apiError, mensajeError } from '../utils/errors'
import { fmt, fmtFecha, hoyISO, sumarDias } from '../utils/format'

const HORIZONTES = [1, 7, 14] as const
const ESTILO_ESTADO: Record<string, string> = {
  borrador: 'bg-muted/15 text-muted',
  pendiente_aprobacion: 'bg-warn/15 text-warn',
  aprobada: 'bg-good/15 text-good',
  rechazada: 'bg-bad/15 text-bad',
  despachada: 'bg-brand/15 text-brand',
}

/** Wireframe 2a — Dashboard de predicción de demanda y aprobación de cargas de ruta. */
export function SalesDashboardView() {
  const { can } = useAuth()
  const [rutaId, setRutaId] = useState('')
  const [fecha, setFecha] = useState(() => sumarDias(hoyISO(), 1))
  const [horizonte, setHorizonte] = useState<number>(1)
  const [consulta, setConsulta] = useState<{ rutaId: string; fecha: string } | null>(null)

  const rutas = useQuery({ queryKey: ['rutas'], queryFn: listarRutas })
  useEffect(() => {
    if (!rutaId && rutas.data?.length) setRutaId(rutas.data[0].id)
  }, [rutas.data, rutaId])

  const plan = useLoadPlan(consulta?.rutaId ?? null, consulta?.fecha ?? null)
  const modelo = useModelMetrics(90, can('ml:metricas:leer'))

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Dashboard de Ventas</h1>

      <Card titulo="Filtros">
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (rutaId) setConsulta({ rutaId, fecha })
          }}
        >
          <Campo etiqueta="Ruta">
            <select className={CLASE_INPUT} value={rutaId} onChange={(e) => setRutaId(e.target.value)}>
              {rutas.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.codigo} {r.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo etiqueta="Fecha operación">
            <input type="date" className={CLASE_INPUT} value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </Campo>
          <fieldset className="flex flex-col gap-1 text-xs font-medium text-muted">
            <legend className="mb-1">Horizonte</legend>
            <div className="flex gap-3 py-1.5 text-sm text-ink">
              {HORIZONTES.map((h) => (
                <label key={h} className="flex items-center gap-1">
                  <input type="radio" name="horizonte" checked={horizonte === h} onChange={() => setHorizonte(h)} />
                  {h} {h === 1 ? 'día' : 'días'}
                </label>
              ))}
            </div>
          </fieldset>
          <Button type="submit" variant="primary" disabled={!rutaId} className="ml-auto">
            Consultar
          </Button>
        </form>
        {modelo.data && (
          <p className="mt-3 text-xs text-muted">
            Modelo activo: {modelo.data.modelo.algoritmo} {modelo.data.modelo.version} · MAPE{' '}
            <span className="num">{fmt(modelo.data.resumen.mape, ' %')}</span>
          </p>
        )}
        {rutas.isError && <AlertBanner>{mensajeError(rutas.error)}</AlertBanner>}
      </Card>

      {!consulta && (
        <EmptyState titulo="Seleccione una ruta y presione Consultar" detalle="Verá el plan de carga vigente o podrá generarlo." />
      )}
      {consulta && plan.isPending && <Cargando texto="Consultando plan de carga…" />}
      {consulta && plan.isError && <AlertBanner>{mensajeError(plan.error)}</AlertBanner>}
      {consulta && plan.isSuccess && (
        <PlanPanel
          key={`${consulta.rutaId}|${consulta.fecha}`}
          rutaId={consulta.rutaId}
          fecha={consulta.fecha}
          horizonte={horizonte}
          plan={plan.data}
        />
      )}
    </div>
  )
}

function PlanPanel({
  rutaId,
  fecha,
  horizonte,
  plan,
}: {
  rutaId: string
  fecha: string
  horizonte: number
  plan: LoadPlanResponse | null
}) {
  const { can } = useAuth()
  const { mutacion, recalcular } = useLoadPlanActions(rutaId, fecha)
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set())
  const [cantidades, setCantidades] = useState<Cantidades>({})
  const [observaciones, setObservaciones] = useState('')
  const [rechazando, setRechazando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [aviso, setAviso] = useState<string | null>(null)
  const [productoGrafico, setProductoGrafico] = useState('')

  // Reinicia el formulario cuando cambia el plan (id o estado).
  const firma = plan ? `${plan.carga_id}|${plan.estado}` : 'sin-plan'
  useEffect(() => {
    if (!plan) return
    const marcados = new Set<string>()
    const cants: Cantidades = {}
    for (const i of plan.items) {
      const valor = i.cantidad_aprobada ?? i.cantidad_sugerida
      cants[i.producto_id] = String(Number(valor))
      if (Number(valor) > 0) marcados.add(i.producto_id)
    }
    setSeleccion(marcados)
    setCantidades(cants)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firma])

  useEffect(() => {
    if (plan && !plan.items.some((i) => i.producto_id === productoGrafico)) {
      setProductoGrafico(plan.items[0]?.producto_id ?? '')
    }
  }, [plan, productoGrafico])

  const editable = plan?.estado === 'borrador' || plan?.estado === 'pendiente_aprobacion'
  const puedeAprobar = can('carga_ruta:aprobar')
  const puedeGenerar = can('carga_ruta:generar')

  const kpis = useMemo(() => {
    const items = plan?.items ?? []
    const demanda = items.reduce((s, i) => s + Number(i.cantidad_predicha), 0)
    const sugerido = items.reduce((s, i) => s + Number(i.cantidad_sugerida), 0)
    return {
      demanda,
      cobertura: demanda > 0 ? Math.min(100, (sugerido / demanda) * 100) : 100,
      riesgo: items.filter((i) => i.ajustado_por_stock).length,
    }
  }, [plan])

  const pronostico = useDemandForecast({
    productoId: productoGrafico || null,
    rutaId,
    fechaOperacion: fecha,
    horizonte,
    habilitado: can('prediccion:consultar') && plan !== null,
  })
  const puntos: PuntoDemanda[] =
    pronostico.data?.pronosticos[0]?.serie.map((p) => ({
      fecha: p.fecha_objetivo,
      predicha: p.demanda_predicha,
      inferior: p.limite_inferior,
      superior: p.limite_superior,
    })) ?? []

  const ocupado = mutacion.isPending || recalcular.isPending
  const hayErrorCantidad = (plan?.items ?? []).some(
    (i) => seleccion.has(i.producto_id) && errorCantidad(cantidades[i.producto_id] ?? '', i.stock_disponible),
  )
  const error = mutacion.error ?? recalcular.error

  const ejecutar = (s: LoadPlanRequest, mensaje: string) => {
    setAviso(null)
    mutacion.mutate(s, { onSuccess: () => setAviso(mensaje) })
  }

  const aprobar = () => {
    if (!plan) return
    ejecutar(
      {
        accion: 'aprobar',
        carga_id: plan.carga_id,
        observaciones: observaciones || undefined,
        // Filas sin marcar se aprueban en 0: no salen en la carga.
        ajustes: plan.items.map((i) => ({
          producto_id: i.producto_id,
          cantidad_aprobada: seleccion.has(i.producto_id) ? Number(cantidades[i.producto_id]) : 0,
        })),
      },
      'Carga aprobada: stock reservado y movimientos registrados en kardex.',
    )
  }

  if (!plan) {
    return (
      <EmptyState
        titulo="No hay plan de carga vigente para esta ruta y fecha"
        detalle="Genere un plan sugerido a partir de la demanda predicha y el stock disponible."
      >
        {puedeGenerar && (
          <Button
            variant="primary"
            disabled={ocupado}
            onClick={() => ejecutar({ accion: 'generar', ruta_id: rutaId, fecha_operacion: fecha }, 'Plan generado en borrador.')}
          >
            {mutacion.isPending ? 'Generando…' : 'Generar plan sugerido'}
          </Button>
        )}
        {error && <AlertBanner>{mensajeError(error)}</AlertBanner>}
      </EmptyState>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Card titulo="KPIs">
          <dl className="grid grid-cols-3 gap-2 text-center">
            <Kpi etiqueta="Demanda total" valor={`${fmt(kpis.demanda)} u`} />
            <Kpi etiqueta="Cobertura de stock" valor={`${fmt(kpis.cobertura)} %`} />
            <Kpi etiqueta="Ítems en riesgo" valor={String(kpis.riesgo)} alerta={kpis.riesgo > 0} />
          </dl>
        </Card>
        <Card
          titulo="Demanda predicha"
          acciones={
            <select
              aria-label="Producto del gráfico"
              className={`${CLASE_INPUT} max-w-[14rem]`}
              value={productoGrafico}
              onChange={(e) => setProductoGrafico(e.target.value)}
            >
              {plan.items.map((i) => (
                <option key={i.producto_id} value={i.producto_id}>
                  {i.sku} · {i.producto_nombre}
                </option>
              ))}
            </select>
          }
        >
          {!can('prediccion:consultar') ? (
            <p className="py-6 text-center text-sm text-muted">Su rol no tiene permiso para consultar pronósticos.</p>
          ) : pronostico.isPending ? (
            <Cargando />
          ) : pronostico.isError ? (
            <AlertBanner>{mensajeError(pronostico.error)}</AlertBanner>
          ) : (
            <DemandChart puntos={puntos} />
          )}
        </Card>
      </div>

      <Card
        titulo={`Plan de carga sugerido · ${fmtFecha(plan.fecha_operacion)}`}
        acciones={
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${ESTILO_ESTADO[plan.estado]}`}>
            {plan.estado.replace('_', ' ')}
          </span>
        }
      >
        <LoadPlanTable
          items={plan.items}
          editable={editable && puedeAprobar}
          seleccion={seleccion}
          cantidades={cantidades}
          onSeleccion={(id, marcado) =>
            setSeleccion((prev) => {
              const s = new Set(prev)
              if (marcado) s.add(id)
              else s.delete(id)
              return s
            })
          }
          onSeleccionTodos={(marcado) => setSeleccion(marcado ? new Set(plan.items.map((i) => i.producto_id)) : new Set())}
          onCantidad={(id, valor) => setCantidades((prev) => ({ ...prev, [id]: valor }))}
        />
        <p className="mt-2 text-xs text-muted">⚠ Limitado por stock · ⛔ Sin existencia (ver alerta de compras)</p>

        {editable && (
          <div className="mt-3 max-w-xl">
            <Campo etiqueta="Observaciones">
              <input className={CLASE_INPUT} value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
            </Campo>
          </div>
        )}

        <div className="mt-4 space-y-2">
          {aviso && <AlertBanner tipo="exito">{aviso}</AlertBanner>}
          {error && <AlertBanner>{mensajeErrorCarga(error)}</AlertBanner>}
          {editable && (
            <div className="flex flex-wrap justify-end gap-2">
              {plan.estado === 'borrador' && puedeGenerar && puedeAprobar && (
                <Button disabled={ocupado} onClick={() => recalcular.mutate(plan, { onSuccess: () => setAviso('Plan recalculado con el stock actual.') })}>
                  {recalcular.isPending ? 'Recalculando…' : 'Recalcular'}
                </Button>
              )}
              {puedeAprobar && (
                <Button variant="danger" disabled={ocupado} onClick={() => setRechazando(true)}>
                  Rechazar
                </Button>
              )}
              {plan.estado === 'borrador' && puedeGenerar && (
                <Button
                  disabled={ocupado}
                  onClick={() => ejecutar({ accion: 'enviar', carga_id: plan.carga_id, observaciones: observaciones || undefined }, 'Plan enviado a aprobación.')}
                >
                  Enviar a aprobación
                </Button>
              )}
              {puedeAprobar && (
                <Button variant="primary" disabled={ocupado || seleccion.size === 0 || hayErrorCantidad} onClick={aprobar}>
                  ✔ Aprobar
                </Button>
              )}
            </div>
          )}
        </div>
      </Card>

      {rechazando && (
        <Modal
          titulo="Rechazar plan de carga"
          onCerrar={() => setRechazando(false)}
          acciones={
            <>
              <Button onClick={() => setRechazando(false)}>Cancelar</Button>
              <Button
                variant="danger"
                disabled={!motivo.trim() || ocupado}
                onClick={() => {
                  ejecutar({ accion: 'rechazar', carga_id: plan.carga_id, motivo_rechazo: motivo.trim() }, 'Plan rechazado.')
                  setRechazando(false)
                  setMotivo('')
                }}
              >
                Rechazar plan
              </Button>
            </>
          }
        >
          <Campo etiqueta="Motivo del rechazo (obligatorio)">
            <textarea className={CLASE_INPUT} rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
          </Campo>
        </Modal>
      )}
    </div>
  )
}

function mensajeErrorCarga(e: unknown): string {
  const api = apiError(e)
  if (api?.codigo === 'CANTIDAD_EXCEDE_STOCK') {
    return 'Alguna cantidad aprobada excede el stock disponible. Ajuste las cantidades e intente de nuevo.'
  }
  return mensajeError(e)
}

function Kpi({ etiqueta, valor, alerta = false }: { etiqueta: string; valor: string; alerta?: boolean }) {
  return (
    <div className="rounded-md border border-line px-2 py-3">
      <dt className="text-xs text-muted">{etiqueta}</dt>
      <dd className={`num mt-1 text-xl font-semibold ${alerta ? 'text-warn' : ''}`}>{valor}</dd>
    </div>
  )
}
