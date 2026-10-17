import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MatrizAcceso } from '../../types'
import { AccesoPantallasPanel } from './AccesoPantallasPanel'
import { MatrizPermisosPanel } from './MatrizPermisosPanel'

const api = vi.hoisted(() => ({
  obtenerMatriz: vi.fn(),
  reemplazarPermisosRol: vi.fn(),
  actualizarRol: vi.fn(),
  obtenerAccesoUsuario: vi.fn(),
  listarUsuarios: vi.fn(),
}))
vi.mock('../../services/rbacApi', () => api)
vi.mock('../../services/usersApi', () => ({ listarUsuarios: api.listarUsuarios }))

const rol = (o: object): MatrizAcceso['roles'][number] => ({
  id: 1,
  nombre: 'Liquidador',
  descripcion: null,
  activo: true,
  es_sistema: false,
  requiere_proveedor: false,
  color: 'good' as const,
  pantalla_inicio: null,
  total_usuarios: 2,
  permisos: ['liquidaciones:leer'],
  ...o,
})

const MATRIZ: MatrizAcceso = {
  roles: [
    rol({ id: 9, nombre: 'Administrador', es_sistema: true, color: 'bad' as const, permisos: ['liquidaciones:leer', 'liquidaciones:registrar'] }),
    rol({}),
    rol({ id: 2, nombre: 'Gerente', color: 'brand' as const, activo: false, permisos: ['reportes:leer'] }),
  ],
  permisos: [
    { id: 1, codigo: 'liquidaciones:leer', descripcion: null, modulo: 'liquidaciones', activo: true },
    { id: 2, codigo: 'liquidaciones:registrar', descripcion: null, modulo: 'liquidaciones', activo: true },
    { id: 3, codigo: 'reportes:leer', descripcion: null, modulo: 'reportes', activo: true },
  ],
  pantallas: [
    { id: 1, clave: 'liquidacion', etiqueta: 'Liquidación Diaria', ruta: '/ventas/liquidacion', grupo: 'Ventas', orden: 60, activo: true, permisos: ['liquidaciones:registrar'] },
    { id: 2, clave: 'reportes', etiqueta: 'Reportes', ruta: '/reportes', grupo: 'Analítica', orden: 110, activo: true, permisos: ['reportes:leer'] },
  ],
}

function montar(ui: React.ReactElement) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={cliente}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.obtenerMatriz.mockResolvedValue(MATRIZ)
  api.reemplazarPermisosRol.mockResolvedValue(rol({}))
  api.actualizarRol.mockResolvedValue(rol({}))
  api.listarUsuarios.mockResolvedValue({ total: 1, usuarios: [{ id: 'u1', email: 'ana@ds.gt', nombre_completo: 'Ana', activo: true, roles: ['Liquidador'], rutas: [], creado_en: '2026-01-01T00:00:00Z' }] })
})

describe('MatrizPermisosPanel', () => {
  it('pinta la matriz con lo que devuelve la BD y bloquea el rol de sistema', async () => {
    montar(<MatrizPermisosPanel />)
    const celda = await screen.findByLabelText('Liquidador · liquidaciones:leer')
    expect(celda).toBeChecked()
    expect(screen.getByLabelText('Liquidador · liquidaciones:registrar')).not.toBeChecked()
    expect(screen.getByLabelText('Administrador · liquidaciones:registrar')).toBeDisabled()
  })

  it('marcar un permiso muestra el cambio y guarda el conjunto completo del rol', async () => {
    montar(<MatrizPermisosPanel />)
    fireEvent.click(await screen.findByLabelText('Liquidador · liquidaciones:registrar'))
    expect(screen.getByText('Cambios sin guardar')).toBeInTheDocument()
    expect(screen.getByText(/\+ liquidaciones:registrar/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Guardar cambios \(1\)/ }))
    await waitFor(() =>
      expect(api.reemplazarPermisosRol).toHaveBeenCalledWith(1, ['liquidaciones:leer', 'liquidaciones:registrar']),
    )
  })

  it('descartar revierte el borrador sin llamar a la API', async () => {
    montar(<MatrizPermisosPanel />)
    fireEvent.click(await screen.findByLabelText('Liquidador · liquidaciones:leer'))
    fireEvent.click(screen.getByRole('button', { name: 'Descartar' }))
    expect(screen.getByLabelText('Liquidador · liquidaciones:leer')).toBeChecked()
    expect(api.reemplazarPermisosRol).not.toHaveBeenCalled()
  })

  it('activar y desactivar un rol se hace desde la matriz', async () => {
    montar(<MatrizPermisosPanel />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Activar rol Gerente' }))
    await waitFor(() => expect(api.actualizarRol).toHaveBeenCalledWith(2, { activo: true }))
    expect(screen.queryByRole('switch', { name: /rol Administrador/ })).not.toBeInTheDocument()
  })

  it('muestra el motivo si el servidor rechaza el guardado', async () => {
    api.reemplazarPermisosRol.mockRejectedValue({ isAxiosError: true, response: { data: { codigo: 'ROL_SISTEMA_PROTEGIDO', mensaje: 'Rol protegido.' } } })
    montar(<MatrizPermisosPanel />)
    fireEvent.click(await screen.findByLabelText('Liquidador · liquidaciones:registrar'))
    fireEvent.click(screen.getByRole('button', { name: /Guardar cambios/ }))
    expect(await screen.findByText(/Liquidador:/)).toBeInTheDocument()
  })
})

describe('AccesoPantallasPanel', () => {
  it('calcula las pantallas por rol (solo roles activos con algún permiso de la pantalla)', async () => {
    montar(<AccesoPantallasPanel />)
    expect(await screen.findByLabelText('Administrador · Liquidación Diaria: sí')).toBeInTheDocument()
    expect(screen.getByLabelText('Liquidador · Liquidación Diaria: no')).toBeInTheDocument()
    // Gerente tiene reportes:leer pero está inactivo.
    expect(screen.getByLabelText('Gerente · Reportes: no')).toBeInTheDocument()
  })

  it('«ver como usuario» muestra por qué permiso se habilita cada pantalla', async () => {
    api.obtenerAccesoUsuario.mockResolvedValue({
      usuario_id: 'u1',
      nombre_completo: 'Ana',
      activo: true,
      roles: ['Liquidador'],
      permisos: ['liquidaciones:registrar'],
      pantallas: [
        { clave: 'liquidacion', etiqueta: 'Liquidación Diaria', ruta: '/ventas/liquidacion', grupo: 'Ventas', autorizada: true, via_permisos: ['liquidaciones:registrar'] },
        { clave: 'reportes', etiqueta: 'Reportes', ruta: '/reportes', grupo: 'Analítica', autorizada: false, via_permisos: [] },
      ],
    })
    montar(<AccesoPantallasPanel />)
    const combo = await screen.findByRole('combobox')
    await screen.findByText(/Ana · ana@ds.gt/)
    fireEvent.change(combo, { target: { value: 'u1' } })
    expect(await screen.findByText('vía liquidaciones:registrar')).toBeInTheDocument()
    expect(api.obtenerAccesoUsuario).toHaveBeenCalledWith('u1')
  })
})
