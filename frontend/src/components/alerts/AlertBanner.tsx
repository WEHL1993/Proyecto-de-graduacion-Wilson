import { AlertTriangle, Bell } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'
import { useAlertas, useReconocerAlerta } from '../../hooks/useAlerts'
import type { AlertItem, TipoAlerta } from '../../types'
import { mensajeError } from '../../utils/errors'

const ETIQUETA_TIPO: Record<TipoAlerta, string> = {
  stock_bajo: 'Stock bajo',
  quiebre_proyectado: 'Quiebre proyectado',
  mape_umbral: 'MAPE sobre el umbral',
  etl_error: 'Error de carga ETL',
  diferencia_caja: 'Diferencia de caja',
}

// Vista donde se atiende cada tipo de alerta.
// `pantalla` es la clave en la BD (`pantallas.clave`): el enlace solo aparece si el usuario la ve.
const DESTINO: Record<TipoAlerta, { to: string; pantalla: string }> = {
  stock_bajo: { to: '/inventario', pantalla: 'inventario' },
  quiebre_proyectado: { to: '/compras', pantalla: 'compras' },
  mape_umbral: { to: '/monitoreo', pantalla: 'monitoreo' },
  etl_error: { to: '/etl', pantalla: 'etl' },
  diferencia_caja: { to: '/ventas/liquidaciones', pantalla: 'liquidaciones' },
}

const esCritica = (a: AlertItem) => a.severidad === 'critica'

/**
 * Bandeja global de alertas abiertas del usuario conectado (el servidor filtra por rol).
 * Muestra un contador en la cabecera, el listado desplegable con «Reconocer» y, si hay
 * alertas críticas, una franja visible en toda la aplicación.
 */
export function AlertBanner() {
  const { can, puedeVer } = useAuth()
  const [abierto, setAbierto] = useState(false)
  const alertas = useAlertas(can('alertas:leer'))
  const reconocer = useReconocerAlerta()

  if (!can('alertas:leer')) return null
  const lista = alertas.data?.alertas ?? []
  const total = alertas.data?.total ?? 0
  const criticas = lista.filter(esCritica).length

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={abierto}
        aria-controls="bandeja-alertas"
        onClick={() => setAbierto((v) => !v)}
        className="relative rounded-lg p-2 text-muted hover:bg-surface hover:text-ink"
      >
        <Bell aria-hidden className="h-5 w-5" />
        {total > 0 && (
          <span
            aria-hidden
            className={`num absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 text-[10px] font-bold text-white ${criticas > 0 ? 'bg-bad' : 'bg-brand'}`}
          >
            {total > 99 ? '99+' : total}
          </span>
        )}
        <span className="sr-only">
          {total} {total === 1 ? 'alerta' : 'alertas'}
          {criticas > 0 && ` (${criticas} crítica${criticas > 1 ? 's' : ''})`}
        </span>
      </button>

      {abierto && (
        <div
          id="bandeja-alertas"
          className="absolute right-0 z-40 mt-1 max-h-96 w-[26rem] max-w-[90vw] overflow-auto rounded-xl border border-line bg-panel p-2 shadow-lg"
        >
          {reconocer.isError && (
            <p role="alert" className="px-2 py-1 text-xs text-bad">
              {mensajeError(reconocer.error)}
            </p>
          )}
          {alertas.isError ? (
            <p role="alert" className="px-2 py-3 text-sm text-bad">
              {mensajeError(alertas.error)}
            </p>
          ) : lista.length ? (
            <ul>
              {lista.map((a) => {
                const destino = DESTINO[a.tipo]
                return (
                  <li key={a.id} className="border-b border-line px-2 py-2 last:border-0">
                    <p className={`text-xs font-semibold uppercase ${esCritica(a) ? 'text-bad' : 'text-muted'}`}>
                      {a.severidad} · {ETIQUETA_TIPO[a.tipo]}
                    </p>
                    <p className="text-sm">{a.mensaje}</p>
                    <div className="mt-1 flex items-center gap-3 text-xs">
                      <button
                        type="button"
                        disabled={reconocer.isPending && reconocer.variables === a.id}
                        onClick={() => reconocer.mutate(a.id)}
                        aria-label={`Reconocer alerta: ${ETIQUETA_TIPO[a.tipo]}`}
                        className="rounded border border-line px-2 py-0.5 hover:bg-surface disabled:opacity-50"
                      >
                        Reconocer
                      </button>
                      {puedeVer(destino.pantalla) && (
                        <Link to={destino.to} onClick={() => setAbierto(false)} className="text-brand underline">
                          Ir a resolver
                        </Link>
                      )}
                    </div>
                  </li>
                )
              })}
              {total > lista.length && (
                <li className="px-2 py-2 text-xs text-muted">
                  Mostrando {lista.length} de {total} alertas abiertas.
                </li>
              )}
            </ul>
          ) : (
            <p className="px-2 py-3 text-sm text-muted">Sin alertas abiertas.</p>
          )}
        </div>
      )}
    </div>
  )
}

/** Franja de aviso en el encabezado del contenido cuando existen alertas críticas abiertas. */
export function FranjaAlertasCriticas() {
  const { can } = useAuth()
  const { data } = useAlertas(can('alertas:leer'))
  const criticas = data?.alertas.filter(esCritica) ?? []
  if (!criticas.length) return null
  return (
    <div role="alert" className="border-b border-bad bg-bad/10 px-4 py-2 text-sm">
      <AlertTriangle aria-hidden className="mr-2 inline h-4 w-4 -translate-y-px text-bad" />
      <strong className="text-bad">
        {criticas.length === 1 ? 'Alerta crítica: ' : `${criticas.length} alertas críticas. Primera: `}
      </strong>
      {criticas[0].mensaje}
    </div>
  )
}
