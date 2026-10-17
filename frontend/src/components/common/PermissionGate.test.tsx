import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { AuthProvider } from '../../app/providers/AuthProvider'
import { AppShell } from '../layout/AppShell'
import { PermissionGate } from './PermissionGate'

// ADR-19: el menú viene de la BD. Este mapa solo simula lo que el servidor devolvería.
const PANTALLAS = [
  { clave: 'dashboard', etiqueta: 'Dashboard de Ventas', ruta: '/', grupo: 'Ventas', orden: 10, requiere: ['carga_ruta:generar', 'carga_ruta:aprobar'] },
  { clave: 'monitoreo', etiqueta: 'Monitoreo de Modelos', ruta: '/monitoreo', grupo: 'Analítica', orden: 20, requiere: ['ml:metricas:leer'] },
]

function sembrarSesion(permisos: string[]) {
  const menu = PANTALLAS.filter((p) => p.requiere.some((r) => permisos.includes(r))).map(({ requiere: _r, ...p }) => p)
  localStorage.setItem(
    'ds.session',
    JSON.stringify({
      token: 't',
      expiraEn: Date.now() + 3_600_000,
      usuario: { id: 'u1', nombre_completo: 'Ana Ventas', roles: ['EncargadoVentas'], permisos, menu, pantalla_inicio: menu[0]?.ruta ?? null },
    }),
  )
}

function montar(ruta: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[ruta]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>pantalla login</p>} />
            <Route path="/acceso-denegado" element={<p>acceso denegado</p>} />
            <Route
              element={
                <PermissionGate guardRoute anyOf={[]}>
                  <AppShell />
                </PermissionGate>
              }
            >
              <Route path="/" element={<p>dashboard</p>} />
              <Route
                path="/monitoreo"
                element={
                  <PermissionGate guardRoute pantalla="monitoreo">
                    <p>panel de monitoreo</p>
                  </PermissionGate>
                }
              />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TC-RBAC-04: rutas protegidas por permiso', () => {
  beforeEach(() => localStorage.clear())

  it('sin sesión redirige a /login', () => {
    montar('/monitoreo')
    expect(screen.getByText('pantalla login')).toBeInTheDocument()
  })

  it('Ventas navegando a /monitoreo termina en acceso denegado', () => {
    sembrarSesion(['carga_ruta:generar', 'carga_ruta:aprobar', 'prediccion:consultar'])
    montar('/monitoreo')
    expect(screen.getByText('acceso denegado')).toBeInTheDocument()
    expect(screen.queryByText('panel de monitoreo')).not.toBeInTheDocument()
  })

  it('el menú de Ventas muestra Dashboard y oculta Monitoreo', () => {
    sembrarSesion(['carga_ruta:generar'])
    montar('/')
    expect(screen.getByRole('link', { name: 'Dashboard de Ventas' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Monitoreo de Modelos' })).not.toBeInTheDocument()
  })

  it('Gerente con ml:metricas:leer ve el panel y su enlace', () => {
    sembrarSesion(['carga_ruta:aprobar', 'ml:metricas:leer'])
    montar('/monitoreo')
    expect(screen.getByText('panel de monitoreo')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Monitoreo de Modelos' })).toBeInTheDocument()
  })

  it('modo elemento: muestra el fallback si falta el permiso', () => {
    sembrarSesion(['ml:metricas:leer'])
    render(
      <MemoryRouter>
        <AuthProvider>
          <PermissionGate anyOf={['ml:reentrenar']} fallback={<span>solo lectura</span>}>
            <button>Reentrenar</button>
          </PermissionGate>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(screen.getByText('solo lectura')).toBeInTheDocument()
    expect(screen.queryByText('Reentrenar')).not.toBeInTheDocument()
  })
})
