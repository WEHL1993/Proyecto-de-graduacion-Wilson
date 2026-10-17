import { BarChart3, X } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import type { PantallaMenu as MenuItem } from '../../types'
import { iconoDePantalla } from './iconos'

interface Props {
  menu: readonly MenuItem[]
  colapsado: boolean
  /** Escritorio: el puntero (o el foco) sobre el menú lo expande. */
  alExpandir: () => void
  /** Solo en móvil: el menú es un panel deslizable. */
  abierto: boolean
  alCerrar: () => void
}

/** Agrupa el menú por `grupo` conservando el orden en que llega del servidor. */
function agrupar(menu: readonly MenuItem[]) {
  const grupos = new Map<string, MenuItem[]>()
  for (const n of menu) grupos.set(n.grupo ?? 'General', [...(grupos.get(n.grupo ?? 'General') ?? []), n])
  return [...grupos.entries()]
}

export function Sidebar({ menu, colapsado, alExpandir, abierto, alCerrar }: Props) {
  const { pathname } = useLocation()
  // En móvil el panel siempre se muestra completo; el modo colapsado solo aplica en escritorio.
  const compacto = colapsado

  return (
    <div className={`transition-[width] duration-200 md:shrink-0 ${compacto ? 'md:w-[72px]' : 'md:w-64'}`}>
      {abierto && <div className="fixed inset-0 z-30 bg-navy/50 md:hidden" onClick={alCerrar} aria-hidden />}
      <aside
        onMouseEnter={alExpandir}
        onFocus={alExpandir}
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy text-blue-100 shadow-xl transition-[transform,width] duration-200 md:translate-x-0 ${
          abierto ? 'translate-x-0' : '-translate-x-full'
        } ${compacto ? 'md:w-[72px] md:shadow-none' : 'md:w-64'}`}
      >
        <div className={`flex h-16 shrink-0 items-center gap-3 border-b border-white/10 px-4 ${compacto ? 'md:justify-center md:px-0' : ''}`}>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/15 text-white">
            <BarChart3 className="h-5 w-5" aria-hidden />
          </span>
          <div className={`min-w-0 leading-tight ${compacto ? 'md:hidden' : ''}`}>
            <p className="truncate text-sm font-bold text-white">DS Predictive</p>
            <p className="truncate text-[11px] text-blue-200">Análisis predictivo de demanda</p>
          </div>
          <button
            type="button"
            onClick={alCerrar}
            aria-label="Cerrar menú"
            className="ml-auto rounded-md p-1.5 text-blue-200 hover:bg-white/10 md:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav aria-label="Principal" className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {agrupar(menu).map(([grupo, items]) => (
            <div key={grupo}>
              <p
                className={`mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-blue-300/80 ${compacto ? 'md:hidden' : ''}`}
              >
                {grupo}
              </p>
              {compacto && <div className="mx-3 mb-2 hidden border-t border-white/10 md:block" aria-hidden />}
              <ul className="space-y-1">
                {items.map((n) => {
                  const Icono = iconoDePantalla(n.clave)
                  return (
                    <li key={n.clave}>
                      <NavLink
                        to={n.ruta}
                        end
                        title={compacto ? n.etiqueta : undefined}
                        className={({ isActive }) => {
                          // «Rutas» agrupa varias pantallas (/catalogos/*): queda activa en todas.
                          const activa = isActive || (!!n.ruta_prefijo && pathname.startsWith(n.ruta_prefijo))
                          return `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                            compacto ? 'md:justify-center' : ''
                          } ${activa ? 'bg-white/15 font-semibold text-white' : 'text-blue-100 hover:bg-white/10 hover:text-white'}`
                        }}
                      >
                        {({ isActive }) => {
                          const activa = isActive || (!!n.ruta_prefijo && pathname.startsWith(n.ruta_prefijo))
                          return (
                            <>
                              {activa && <span aria-hidden className="absolute -left-3 h-6 w-1 rounded-r bg-sky-300" />}
                              <Icono aria-hidden className="h-[18px] w-[18px] shrink-0" />
                              <span className={`truncate ${compacto ? 'md:sr-only' : ''}`}>{n.etiqueta}</span>
                            </>
                          )
                        }}
                      </NavLink>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

      </aside>
    </div>
  )
}
