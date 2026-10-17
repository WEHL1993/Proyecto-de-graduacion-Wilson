import { ChevronDown, LogOut, Menu } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../../app/providers/AuthProvider'
import { AlertBanner } from '../alerts/AlertBanner'

interface Props {
  titulo: string
  grupo?: string
  alAbrirMenu: () => void
}

const iniciales = (nombre: string) =>
  nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')

function MenuUsuario() {
  const { usuario, logout } = useAuth()
  const [abierto, setAbierto] = useState(false)
  const contenedor = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierto) return
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false)
    }
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setAbierto(false)
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('keydown', escape)
    }
  }, [abierto])

  const nombre = usuario?.nombre_completo ?? ''
  const roles = usuario?.roles.join(', ') ?? ''

  return (
    <div ref={contenedor} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
        className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 hover:bg-surface"
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-navy text-xs font-semibold text-white">
          {iniciales(nombre)}
        </span>
        <span className="hidden text-left leading-tight sm:block">
          <span className="block max-w-[10rem] truncate text-sm font-semibold text-ink">{nombre}</span>
          <span className="block max-w-[10rem] truncate text-xs text-muted">{roles}</span>
        </span>
        <ChevronDown aria-hidden className="hidden h-4 w-4 text-muted sm:block" />
      </button>

      {abierto && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-60 overflow-hidden rounded-xl border border-line bg-panel shadow-lg"
        >
          <div className="border-b border-line px-4 py-3">
            <p className="truncate text-sm font-semibold text-ink">{nombre}</p>
            <p className="truncate text-xs text-muted">{roles}</p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={logout}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-bad hover:bg-bad/5"
          >
            <LogOut aria-hidden className="h-4 w-4" />
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  )
}

export function Navbar({ titulo, grupo, alAbrirMenu }: Props) {
  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-panel/90 px-4 backdrop-blur md:px-6">
      <button
        type="button"
        onClick={alAbrirMenu}
        aria-label="Abrir menú"
        className="rounded-lg p-2 text-muted hover:bg-surface hover:text-ink md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>
      <div className="min-w-0 leading-tight">
        {grupo && <p className="truncate text-xs text-muted">{grupo}</p>}
        <p className="truncate text-base font-semibold text-navy">{titulo}</p>
      </div>
      <div className="ml-auto flex items-center gap-2 text-sm">
        <AlertBanner />
        <span className="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden />
        <MenuUsuario />
      </div>
    </header>
  )
}
