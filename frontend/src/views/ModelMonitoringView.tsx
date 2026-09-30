import { useEffect, useState } from 'react'
import { MapeTrendChart } from '../components/charts/MapeTrendChart'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { PermissionGate } from '../components/common/PermissionGate'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import {
  useGuardarConfig,
  useMlConfig,
  useModelMetrics,
  useModelos,
  useRetrain,
} from '../hooks/useModelMetrics'
import type { Algoritmo, MetricsResponse, ModeloResumen } from '../types'
import { apiError, mensajeError } from '../utils/errors'
import { fmt, fmtFecha, semaforoMape } from '../utils/format'
import type { Semaforo } from '../utils/format'

const PERIODOS = [
  { dias: 30, etiqueta: 'Últimos 30 d' },
  { dias: 90, etiqueta: 'Últimos 90 d' },
  { dias: 180, etiqueta: 'Últimos 180 d' },
]

const SEMAFORO: Record<Semaforo, { icono: string; texto: string; clase: string }> = {
  verde: { icono: '🟢', texto: 'Dentro del umbral', clase: 'text-good' },
  amarillo: { icono: '🟡', texto: 'Cerca del umbral', clase: 'text-warn' },
  rojo: { icono: '🔴', texto: 'Sobre el umbral', clase: 'text-bad' },
  sin_dato: { icono: '⚪', texto: 'Sin dato', clase: 'text-muted' },
}

const ALGORITMOS: { valor: Algoritmo; etiqueta: string; disponible: boolean }[] = [
  { valor: 'xgboost', etiqueta: 'XGBoost', disponible: true },
  { valor: 'lstm', etiqueta: 'LSTM (extra opcional, no instalado)', disponible: false },
  { valor: 'sklearn', etiqueta: 'RandomForest', disponible: true },
]

/** Wireframe 2b — Panel de monitoreo de precisión de modelos. */
export function ModelMonitoringView() {
  const [dias, setDias] = useState(90)
  const metricas = useModelMetrics(dias)
  const modelos = useModelos()

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Monitoreo de Modelos ML</h1>
        <div className="flex items-center gap-4 text-sm">
          {metricas.data && (
            <span>
              Modelo en producción:{' '}
              <strong>
                {metricas.data.modelo.algoritmo} {metricas.data.modelo.version}
              </strong>
            </span>
          )}
          <select
            aria-label="Periodo"
            className={CLASE_INPUT}
            value={dias}
            onChange={(e) => setDias(Number(e.target.value))}
          >
            {PERIODOS.map((p) => (
              <option key={p.dias} value={p.dias}>
                {p.etiqueta}
              </option>
            ))}
          </select>
        </div>
      </div>

      {metricas.isPending && <Cargando texto="Cargando métricas…" />}
      {metricas.isError &&
        (apiError(metricas.error)?.codigo === 'SIN_MODELO_PRODUCTIVO' ? (
          <EmptyState
            titulo="Aún no hay un modelo en producción"
            detalle="Entrene y promueva un modelo para ver su precisión y su estado de degradación."
          />
        ) : (
          <AlertBanner>{mensajeError(metricas.error)}</AlertBanner>
        ))}
      {metricas.data && <Panel datos={metricas.data} modelos={modelos.data ?? []} />}
    </div>
  )
}

function Panel({ datos, modelos }: { datos: MetricsResponse; modelos: ModeloResumen[] }) {
  const { degradacion: deg, resumen, serie } = datos
  const previo = serie.length > 1 ? serie[serie.length - 2] : null
  const semaforo = SEMAFORO[semaforoMape(resumen.mape, deg.umbral_mape)]

  return (
    <>
      {deg.requiere_reentrenamiento && (
        <AlertBanner>
          Degradación detectada: el MAPE superó el umbral durante {deg.periodos_consecutivos_actuales} periodos
          consecutivos. Se encoló un reentrenamiento automático.
        </AlertBanner>
      )}

      <section aria-label="Indicadores" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard etiqueta="MAE" valor={fmt(resumen.mae, ' u')} delta={delta(resumen.mae, previo?.mae, ' vs. periodo ant.')} />
        <KpiCard etiqueta="RMSE" valor={fmt(resumen.rmse, ' u')} delta={delta(resumen.rmse, previo?.rmse, ' vs. periodo ant.')} />
        <KpiCard
          etiqueta="MAPE"
          valor={fmt(resumen.mape, ' %')}
          semaforo={semaforo}
          delta={delta(resumen.mape, serie[0]?.mape, ' pts vs. inicio')}
        />
        <div className="rounded-lg border border-line bg-panel p-4">
          <p className="text-xs font-medium text-muted">Estado de degradación</p>
          <p className="num mt-1 text-sm">Umbral MAPE: {fmt(deg.umbral_mape, ' %')}</p>
          <p className="num mt-1 text-sm">
            Periodos consecutivos sobre umbral:{' '}
            <strong className={deg.requiere_reentrenamiento ? 'text-bad' : ''}>
              {deg.periodos_consecutivos_actuales} de {deg.periodos_consecutivos_requeridos}
            </strong>
          </p>
        </div>
      </section>

      <Card titulo="Evolución de MAPE">
        <MapeTrendChart serie={serie} umbral={deg.umbral_mape} />
      </Card>

      <Card titulo="Precisión por producto (peor desempeño)">
        {datos.peores_productos?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-2">Producto</th>
                  <th className="py-2 text-right">MAE</th>
                  <th className="py-2 text-right">RMSE</th>
                  <th className="py-2 text-right">MAPE</th>
                  <th className="py-2 pl-4">Tendencia</th>
                </tr>
              </thead>
              <tbody>
                {datos.peores_productos.map((p) => (
                  <tr key={p.producto_id} className="border-b border-line last:border-0">
                    <td className="py-2">
                      {p.nombre ?? p.producto_id} <span className="font-mono text-xs text-muted">{p.sku}</span>
                    </td>
                    <td className="num py-2 text-right">{fmt(p.mae)}</td>
                    <td className="num py-2 text-right">{fmt(p.rmse)}</td>
                    <td className="num py-2 text-right">{fmt(p.mape, ' %')}</td>
                    <td className="py-2 pl-4">
                      <Tendencia valor={p.tendencia} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-muted">Sin métricas por producto en este rango.</p>
        )}
      </Card>

      <PermissionGate
        anyOf={['ml:reentrenar']}
        fallback={<p className="text-xs text-muted">Su rol puede consultar las métricas, pero no reentrenar.</p>}
      >
        <TriggerReentrenamiento datos={datos} modelos={modelos} />
      </PermissionGate>

      <Card titulo="Historial de modelos">
        {modelos.length ? (
          <ul className="flex flex-wrap gap-2 text-sm">
            {modelos.map((m) => (
              <li
                key={m.id}
                className={`rounded-full border px-3 py-1 ${m.estado === 'produccion' ? 'border-brand font-semibold text-brand' : 'border-line text-muted'}`}
              >
                {m.version} {m.algoritmo} · {m.estado === 'produccion' ? '▶ PROD' : m.estado}
                {m.mape_holdout != null && <span className="num"> · {fmt(m.mape_holdout, ' %')}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Sin modelos registrados.</p>
        )}
      </Card>
    </>
  )
}

function TriggerReentrenamiento({ datos, modelos }: { datos: MetricsResponse; modelos: ModeloResumen[] }) {
  const config = useMlConfig()
  const guardar = useGuardarConfig()
  const { disparo, job, jobId, olvidar } = useRetrain()
  const [umbral, setUmbral] = useState('')
  const [periodos, setPeriodos] = useState('')
  const [algoritmos, setAlgoritmos] = useState<Set<Algoritmo>>(new Set(['xgboost']))
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [guardado, setGuardado] = useState(false)

  useEffect(() => {
    if (config.data) {
      setUmbral(String(config.data.umbral_mape))
      setPeriodos(String(config.data.periodos_consecutivos))
    }
  }, [config.data])

  const umbralNum = Number(umbral)
  const periodosNum = Number(periodos)
  const configValida = umbralNum > 0 && Number.isInteger(periodosNum) && periodosNum >= 1
  const ventanaValida = !desde || !hasta || desde < hasta
  const jobActivo = jobId !== null && job.data?.estado !== 'completado' && job.data?.estado !== 'fallido'
  const ultimo = datos.degradacion.ultimo_reentrenamiento
  const resultado = datos.degradacion.ultimo_reentrenamiento_resultado
  const candidato = modelos.find((m) => m.id === job.data?.resultado_modelo_id)

  return (
    <Card titulo="Trigger de reentrenamiento">
      <div className="flex flex-wrap items-end gap-4">
        <Campo etiqueta="Umbral MAPE (%)">
          <input
            type="number"
            min={0.1}
            step={0.5}
            className={`${CLASE_INPUT} w-28`}
            value={umbral}
            onChange={(e) => {
              setUmbral(e.target.value)
              setGuardado(false)
            }}
          />
        </Campo>
        <Campo etiqueta="Periodos consecutivos">
          <input
            type="number"
            min={1}
            className={`${CLASE_INPUT} w-28`}
            value={periodos}
            onChange={(e) => {
              setPeriodos(e.target.value)
              setGuardado(false)
            }}
          />
        </Campo>
        <Button
          disabled={!configValida || guardar.isPending}
          onClick={() =>
            guardar.mutate({ umbral_mape: umbralNum, periodos_consecutivos: periodosNum }, { onSuccess: () => setGuardado(true) })
          }
        >
          Guardar umbral
        </Button>
        {guardado && <span className="text-sm text-good">✔ Guardado</span>}
      </div>
      {guardar.isError && <AlertBanner>{mensajeError(guardar.error)}</AlertBanner>}

      <fieldset className="mt-4">
        <legend className="mb-1 text-xs font-medium text-muted">Algoritmos candidatos</legend>
        <div className="flex flex-wrap gap-4 text-sm">
          {ALGORITMOS.map((a) => (
            <label key={a.valor} className={`flex items-center gap-1.5 ${a.disponible ? '' : 'text-muted'}`}>
              <input
                type="checkbox"
                disabled={!a.disponible}
                checked={algoritmos.has(a.valor)}
                onChange={(e) =>
                  setAlgoritmos((prev) => {
                    const s = new Set(prev)
                    if (e.target.checked) s.add(a.valor)
                    else s.delete(a.valor)
                    return s
                  })
                }
              />
              {a.etiqueta}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <Campo etiqueta="Ventana de datos: desde">
          <input type="date" className={CLASE_INPUT} value={desde} onChange={(e) => setDesde(e.target.value)} />
        </Campo>
        <Campo etiqueta="hasta (vacío = hoy)">
          <input type="date" className={CLASE_INPUT} value={hasta} onChange={(e) => setHasta(e.target.value)} />
        </Campo>
        {!ventanaValida && <span className="text-sm text-bad">«Desde» debe ser anterior a «hasta».</span>}
      </div>

      <p className="mt-4 text-sm text-muted">
        Último reentrenamiento: {ultimo ? fmtFecha(ultimo) : 'nunca'}
        {resultado && ` (candidato ${resultado === 'produccion' ? 'promovido' : resultado})`}
      </p>

      <div className="mt-3 flex justify-end">
        <Button variant="primary" disabled={algoritmos.size === 0 || !ventanaValida || jobActivo} onClick={() => setConfirmando(true)}>
          ⟳ Reentrenar ahora
        </Button>
      </div>

      {disparo.isError && (
        <div className="mt-3">
          <AlertBanner>{mensajeError(disparo.error)}</AlertBanner>
        </div>
      )}
      {jobId && (
        <div className="mt-3" aria-live="polite">
          <AlertBanner tipo={job.data?.estado === 'fallido' ? 'error' : job.data?.estado === 'completado' ? 'exito' : 'info'}>
            Job <span className="font-mono text-xs">{jobId.slice(0, 8)}</span>:{' '}
            {job.data ? job.data.estado.replace('_', ' ') : 'consultando…'}
            {job.data?.estado === 'completado' &&
              (candidato
                ? ` — candidato ${candidato.version} ${candidato.estado === 'produccion' ? 'promovido a producción' : candidato.estado}.`
                : '.')}
            {job.data?.error && ` ${job.data.error}`}
            {(job.data?.estado === 'completado' || job.data?.estado === 'fallido') && (
              <button type="button" onClick={olvidar} className="ml-3 text-xs text-brand underline">
                Cerrar
              </button>
            )}
          </AlertBanner>
        </div>
      )}

      {confirmando && (
        <Modal
          titulo="Confirmar reentrenamiento"
          onCerrar={() => setConfirmando(false)}
          acciones={
            <>
              <Button onClick={() => setConfirmando(false)}>Cancelar</Button>
              <Button
                variant="primary"
                onClick={() => {
                  disparo.mutate({
                    algoritmos: [...algoritmos],
                    motivo: 'manual',
                    ventana_desde: desde || undefined,
                    ventana_hasta: hasta || undefined,
                    promover_automaticamente: true,
                  })
                  setConfirmando(false)
                }}
              >
                Reentrenar
              </Button>
            </>
          }
        >
          <p>
            Se entrenará un candidato con <strong>{[...algoritmos].join(', ')}</strong> en segundo plano. Solo se
            promoverá a producción si su MAPE mejora al del modelo actual.
          </p>
        </Modal>
      )}
    </Card>
  )
}

function delta(actual: number | null | undefined, previo: number | null | undefined, sufijo: string) {
  if (actual == null || previo == null) return null
  const d = actual - previo
  return { texto: `${d > 0 ? '▲' : d < 0 ? '▼' : '▬'} ${fmt(Math.abs(d))}${sufijo}`, sube: d > 0 }
}

function KpiCard({
  etiqueta,
  valor,
  delta: d,
  semaforo,
}: {
  etiqueta: string
  valor: string
  delta: { texto: string; sube: boolean } | null
  semaforo?: { icono: string; texto: string; clase: string }
}) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <p className="text-xs font-medium text-muted">{etiqueta}</p>
      <p className="num mt-1 text-2xl font-semibold">
        {valor}
        {semaforo && (
          <span className="ml-2 text-base" title={semaforo.texto}>
            <span aria-hidden>{semaforo.icono}</span>
            <span className={`ml-1 text-xs font-medium ${semaforo.clase}`}>{semaforo.texto}</span>
          </span>
        )}
      </p>
      {d && <p className={`num mt-1 text-xs ${d.sube ? 'text-bad' : 'text-good'}`}>{d.texto}</p>}
    </div>
  )
}

function Tendencia({ valor }: { valor: 'sube' | 'baja' | 'estable' | null | undefined }) {
  if (!valor) return <span className="text-muted">—</span>
  const mapa = {
    sube: { icono: '▲', texto: 'Empeora', clase: 'text-bad' },
    baja: { icono: '▼', texto: 'Mejora', clase: 'text-good' },
    estable: { icono: '▬', texto: 'Estable', clase: 'text-muted' },
  }[valor]
  return (
    <span className={mapa.clase}>
      <span aria-hidden>{mapa.icono}</span> {mapa.texto}
    </span>
  )
}
