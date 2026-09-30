import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'
import { PERMISOS_VISTA } from '../../app/rbac'
import { listarAlertas } from '../../services/catalogApi'

const NAV = [
  { to: '/', etiqueta: 'Dashboard de Ventas', permisos: PERMISOS_VISTA.dashboard },
  { to: '/monitoreo', etiqueta: 'Monitoreo de Modelos', permisos: PERMISOS_VISTA.monitoreo },
] as const

export function AppShell() {
  const { usuario, canAny, can, logout } = useAuth()
  const [abierto, setAbierto] = useState(false)

  const alertas = useQuery({
    queryKey: ['alertas'],
    queryFn: listarAlertas,
    enabled: can('alertas:leer'),
    refetchInterval: 60_000,
  })
  const total = alertas.data?.total ?? 0
  const criticas = alertas.data?.alertas.filter((a) => a.severidad === 'critica').length ?? 0

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-line bg-panel md:w-56 md:border-b-0 md:border-r">
        <div className="px-4 py-4 text-sm font-bold tracking-tight">DS Predictive</div>
        <nav aria-label="Principal" className="flex gap-1 px-2 pb-2 md:flex-col">
          {NAV.filter((n) => canAny(n.permisos)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm ${isActive ? 'bg-brand/10 font-semibold text-brand' : 'text-ink hover:bg-surface'}`
              }
            >
              {n.etiqueta}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b border-line bg-panel px-4 py-2.5 text-sm">
          {can('alertas:leer') && (
            <div className="relative">
              <button
                type="button"
                aria-expanded={abierto}
                onClick={() => setAbierto((v) => !v)}
                className="rounded-md px-2 py-1 hover:bg-surface"
              >
                <span aria-hidden>🔔</span>{' '}
                <span className="num">
                  {total} {total === 1 ? 'alerta' : 'alertas'}
                </span>
                {criticas > 0 && <span className="ml-1 font-semibold text-bad">({criticas} crítica{criticas > 1 ? 's' : ''})</span>}
              </button>
              {abierto && (
                <ul className="absolute right-0 z-40 mt-1 max-h-80 w-96 max-w-[90vw] overflow-auto rounded-lg border border-line bg-panel p-2 shadow-lg">
                  {alertas.data?.alertas.length ? (
                    alertas.data.alertas.map((a) => (
                      <li key={a.id} className="border-b border-line px-2 py-2 last:border-0">
                        <p className={`text-xs font-semibold uppercase ${a.severidad === 'critica' ? 'text-bad' : 'text-muted'}`}>
                          {a.severidad} · {a.tipo}
                        </p>
                        <p className="text-sm">{a.mensaje}</p>
                      </li>
                    ))
                  ) : (
                    <li className="px-2 py-3 text-sm text-muted">Sin alertas abiertas.</li>
                  )}
                </ul>
              )}
            </div>
          )}
          <span>
            <span aria-hidden>👤</span> {usuario?.nombre_completo}
            <span className="ml-1 text-muted">({usuario?.roles.join(', ')})</span>
          </span>
          <button type="button" onClick={logout} className="rounded-md px-2 py-1 text-muted hover:bg-surface hover:text-ink">
            Salir
          </button>
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
