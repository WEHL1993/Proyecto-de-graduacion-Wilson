import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'
import { PERMISOS_VISTA } from '../../app/rbac'
import { AlertBanner, FranjaAlertasCriticas } from '../alerts/AlertBanner'

const NAV = [
  { to: '/', etiqueta: 'Dashboard de Ventas', permisos: PERMISOS_VISTA.dashboard },
  { to: '/monitoreo', etiqueta: 'Monitoreo de Modelos', permisos: PERMISOS_VISTA.monitoreo },
  { to: '/compras', etiqueta: 'Abastecimiento', permisos: PERMISOS_VISTA.compras },
  { to: '/inventario', etiqueta: 'Inventario y Kardex', permisos: PERMISOS_VISTA.inventario },
  { to: '/productos', etiqueta: 'Productos', permisos: PERMISOS_VISTA.productos },
  { to: '/ventas/liquidacion', etiqueta: 'Liquidación Diaria', permisos: PERMISOS_VISTA.liquidacion },
  { to: '/ventas/liquidaciones', etiqueta: 'Historial de Liquidaciones', permisos: PERMISOS_VISTA.liquidaciones },
  { to: '/catalogos/rutas', etiqueta: 'Rutas', permisos: PERMISOS_VISTA.catalogos, prefijo: '/catalogos' },
  { to: '/etl', etiqueta: 'Carga de Datos (ETL)', permisos: PERMISOS_VISTA.etl },
  { to: '/politica-datos', etiqueta: 'Política de Datos', permisos: PERMISOS_VISTA.etlConfig },
  { to: '/reportes', etiqueta: 'Reportes', permisos: PERMISOS_VISTA.reportes },
  { to: '/usuarios', etiqueta: 'Usuarios y Roles', permisos: PERMISOS_VISTA.usuarios },
] as const

export function AppShell() {
  const { usuario, canAny, logout } = useAuth()
  const { pathname } = useLocation()

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-line bg-panel md:w-56 md:border-b-0 md:border-r">
        <div className="px-4 py-4 text-sm font-bold tracking-tight">DS Predictive</div>
        <nav aria-label="Principal" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col">
          {NAV.filter((n) => canAny(n.permisos)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) => {
                // «Rutas» agrupa varias pantallas (/catalogos/*): queda activa en todas.
                const activa = isActive || ('prefijo' in n && pathname.startsWith(n.prefijo))
                return `whitespace-nowrap rounded-md px-3 py-2 text-sm ${activa ? 'bg-brand/10 font-semibold text-brand' : 'text-ink hover:bg-surface'}`
              }}
            >
              {n.etiqueta}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b border-line bg-panel px-4 py-2.5 text-sm">
          <AlertBanner />
          <span>
            <span aria-hidden>👤</span> {usuario?.nombre_completo}
            <span className="ml-1 text-muted">({usuario?.roles.join(', ')})</span>
          </span>
          <button type="button" onClick={logout} className="rounded-md px-2 py-1 text-muted hover:bg-surface hover:text-ink">
            Salir
          </button>
        </header>
        <FranjaAlertasCriticas />
        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
