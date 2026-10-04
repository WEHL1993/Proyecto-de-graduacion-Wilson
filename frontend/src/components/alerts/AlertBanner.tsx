import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'
import { PERMISOS_VISTA } from '../../app/rbac'
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
const DESTINO: Record<TipoAlerta, { to: string; permisos: readonly string[] }> = {
  stock_bajo: { to: '/inventario', permisos: PERMISOS_VISTA.inventario },
  quiebre_proyectado: { to: '/compras', permisos: PERMISOS_VISTA.compras },
  mape_umbral: { to: '/monitoreo', permisos: PERMISOS_VISTA.monitoreo },
  etl_error: { to: '/etl', permisos: PERMISOS_VISTA.etl },
  diferencia_caja: { to: '/ventas/liquidaciones', permisos: PERMISOS_VISTA.liquidaciones },
}

const esCritica = (a: AlertItem) => a.severidad === 'critica'

/**
 * Bandeja global de alertas abiertas del usuario conectado (el servidor filtra por rol).
 * Muestra un contador en la cabecera, el listado desplegable con «Reconocer» y, si hay
 * alertas críticas, una franja visible en toda la aplicación.
 */
export function AlertBanner() {
  const { can, canAny } = useAuth()
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
        className="rounded-md px-2 py-1 hover:bg-surface"
      >
        <span aria-hidden>🔔</span>{' '}
        <span className="num">
          {total} {total === 1 ? 'alerta' : 'alertas'}
        </span>
        {criticas > 0 && (
          <span className="ml-1 font-semibold text-bad">
            ({criticas} crítica{criticas > 1 ? 's' : ''})
          </span>
        )}
      </button>

      {abierto && (
        <div
          id="bandeja-alertas"
          className="absolute right-0 z-40 mt-1 max-h-96 w-[26rem] max-w-[90vw] overflow-auto rounded-lg border border-line bg-panel p-2 shadow-lg"
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
                      {canAny(destino.permisos) && (
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
      <span aria-hidden className="mr-2">
        ⛔
      </span>
      <strong className="text-bad">
        {criticas.length === 1 ? 'Alerta crítica: ' : `${criticas.length} alertas críticas. Primera: `}
      </strong>
      {criticas[0].mensaje}
    </div>
  )
}
