import { NavLink } from 'react-router-dom'

const PESTANAS = [
  { to: '/catalogos/rutas', etiqueta: 'Rutas y equipos' },
  { to: '/catalogos/empleados', etiqueta: 'Personal de ruta' },
] as const

/** Pestañas del módulo «Rutas» (M02): rutas y equipos, y personal de ruta. */
export function PestanasRutas() {
  return (
    <nav aria-label="Rutas" className="flex gap-1 border-b border-line">
      {PESTANAS.map((p) => (
        <NavLink
          key={p.to}
          to={p.to}
          end
          className={({ isActive }) =>
            `-mb-px border-b-2 px-4 py-2 text-sm ${isActive ? 'border-brand font-semibold text-brand' : 'border-transparent text-muted hover:text-ink'}`
          }
        >
          {p.etiqueta}
        </NavLink>
      ))}
    </nav>
  )
}
