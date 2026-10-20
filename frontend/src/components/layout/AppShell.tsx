import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'
import { FranjaAlertasCriticas } from '../alerts/AlertBanner'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const { usuario } = useAuth()
  const { pathname } = useLocation()
  // Escritorio: el menú vive contraído; se expande al acercar el puntero y se contrae al pulsar el contenido.
  const [colapsado, setColapsado] = useState(true)
  const [menuAbierto, setMenuAbierto] = useState(false)

  const menu = usuario?.menu ?? []
  // Pantalla actual: coincidencia exacta o, para grupos de rutas (/catalogos/*), por prefijo.
  const actual = menu.find((n) => n.ruta === pathname || (!!n.ruta_prefijo && pathname.startsWith(n.ruta_prefijo)))

  // Al navegar, el panel deslizable de móvil se cierra.
  useEffect(() => setMenuAbierto(false), [pathname])

  return (
    <div className="flex min-h-screen">
      <Sidebar
        menu={menu}
        colapsado={colapsado}
        alExpandir={() => setColapsado(false)}
        abierto={menuAbierto}
        alCerrar={() => setMenuAbierto(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col" onClick={() => !colapsado && setColapsado(true)}>
        <Navbar titulo={pathname === '/recepcion' ? 'Recepción de mercadería' : actual?.etiqueta ?? 'DS Predictive'} grupo={actual?.grupo} alAbrirMenu={() => setMenuAbierto(true)} />
        <FranjaAlertasCriticas />
        <main className="min-w-0 flex-1 p-4 md:p-8">
          <div className="mx-auto w-full max-w-[1600px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
