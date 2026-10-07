import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AxiosError } from 'axios'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RutaAdminOut } from '../types'
import { EmployeesView, textoErrorEmpleado, validarEmpleado } from './EmployeesView'
import { FORM_RUTA_VACIO, RoutesAdminView, textoErrorRuta, validarRuta } from './RoutesAdminView'

const sesion = vi.hoisted(() => ({ permisos: [] as string[] }))
vi.mock('../app/providers/AuthProvider', () => ({
  useAuth: () => ({
    usuario: { id: 'yo', nombre_completo: 'Admin', roles: [], permisos: sesion.permisos },
    can: (p: string) => sesion.permisos.includes(p),
    canAny: (ps: readonly string[]) => ps.some((p) => sesion.permisos.includes(p)),
  }),
}))

const api = vi.hoisted(() => ({
  listarRutasAdmin: vi.fn(),
  equiposIncompletos: vi.fn(),
  rutasDesalineadas: vi.fn(),
  crearRuta: vi.fn(),
  actualizarRuta: vi.fn(),
  desactivarRuta: vi.fn(),
  activarRuta: vi.fn(),
  listarEmpleados: vi.fn(),
  crearEmpleado: vi.fn(),
  actualizarEmpleado: vi.fn(),
  darDeBajaEmpleado: vi.fn(),
  reactivarEmpleado: vi.fn(),
}))
vi.mock('../services/routesAdminApi', () => api)

const ruta = (o: Partial<RutaAdminOut> = {}): RutaAdminOut => ({
  id: 'r1',
  codigo: 'CORNELIO',
  nombre: 'Cornelio',
  zona: null,
  vendedor_id: null,
  activa: true,
  integrantes: 2,
  suma_porcentaje: '100.00',
  equipo_completo: true,
  ...o,
})

const conCodigo = (codigo: string, detalle?: Record<string, unknown>) =>
  new AxiosError('x', '409', undefined, undefined, {
    status: 409,
    data: { codigo, mensaje: 'Mensaje base', detalle },
  } as never)

function montar(vista: 'rutas' | 'empleados') {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>{vista === 'rutas' ? <RoutesAdminView /> : <EmployeesView />}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  sesion.permisos = ['catalogos:leer', 'catalogos:gestionar']
  api.listarRutasAdmin.mockResolvedValue([
    ruta(),
    ruta({ id: 'r2', codigo: 'ANTONIO', nombre: 'Antonio', integrantes: 2, suma_porcentaje: '90.00', equipo_completo: false }),
    ruta({ id: 'r3', codigo: 'CESAR', nombre: 'Cesar', integrantes: 0, suma_porcentaje: '0.00', equipo_completo: false }),
    ruta({ id: 'r4', codigo: 'VIEJA', nombre: 'Vieja', activa: false }),
  ])
  api.equiposIncompletos.mockResolvedValue([
    { ruta_id: 'r2', codigo: 'ANTONIO', nombre: 'Antonio', integrantes: 2, suma_porcentaje: '90.00', tiene_vendedor: true, motivos: ['suma_distinta_de_100'] },
  ])
  api.rutasDesalineadas.mockResolvedValue([])
  api.listarEmpleados.mockResolvedValue({
    items: [
      { id: 'e1', nombre_completo: 'Ana', activo: true, usuario_id: null, creado_en: '' },
      { id: 'e2', nombre_completo: 'Beto', activo: true, usuario_id: 'u1', creado_en: '' },
    ],
    total: 2,
    limit: 25,
    offset: 0,
  })
})

describe('validarRuta / textoErrorRuta', () => {
  it('exige código y nombre al crear; el código no se valida al editar', () => {
    expect(Object.keys(validarRuta(FORM_RUTA_VACIO, false)).sort()).toEqual(['codigo', 'nombre'])
    expect(Object.keys(validarRuta(FORM_RUTA_VACIO, true))).toEqual(['nombre'])
    expect(validarRuta({ codigo: 'CORNELIO', nombre: 'Cornelio', zona: '' }, false)).toEqual({})
  })
  it('limita el código a 20 caracteres', () => {
    expect(validarRuta({ codigo: 'x'.repeat(21), nombre: 'Ruta', zona: '' }, false).codigo).toBeDefined()
  })
  it('agrega el detalle de las bajas bloqueadas', () => {
    expect(textoErrorRuta(conCodigo('RUTA_CON_LIQUIDACIONES', { liquidaciones: ['a', 'b'] }))).toContain('2 en borrador')
    expect(textoErrorRuta(conCodigo('RUTA_CON_CARGAS_VIGENTES', { cargas: ['a'] }))).toContain('1 vigentes')
  })
})

describe('<RoutesAdminView />', () => {
  it('lista las rutas activas con el indicador de reparto 100 %', async () => {
    montar('rutas')
    const fila = (await screen.findByText('Cornelio')).closest('tr')!
    expect(within(fila).getByText(/2 integrantes · 100.00 %/)).toHaveAttribute('data-suma-100', 'si')
    const incompleta = screen.getByText('Antonio', { selector: 'td' }).closest('tr')!
    expect(within(incompleta).getByText(/90.00 %/)).toHaveAttribute('data-suma-100', 'no')
    expect(within(screen.getByText('Cesar', { selector: 'td' }).closest('tr')!).getByText('Sin equipo')).toBeInTheDocument()
    expect(screen.queryByText('Vieja')).not.toBeInTheDocument() // inactiva oculta por defecto
  })

  it('muestra las inactivas al pedirlo y permite activarlas', async () => {
    api.activarRuta.mockResolvedValue(ruta({ id: 'r4' }))
    montar('rutas')
    await screen.findByText('Cornelio')
    fireEvent.click(screen.getByLabelText('Mostrar rutas inactivas'))
    fireEvent.click(await screen.findByRole('button', { name: 'Activar VIEJA' }))
    await waitFor(() => expect(api.activarRuta).toHaveBeenCalledWith('r4'))
  })

  it('lista las rutas con equipo incompleto en el informe', async () => {
    montar('rutas')
    const informe = (await screen.findByText('Rutas con equipo incompleto')).closest('section')!
    expect(await within(informe).findByText(/reparto ≠ 100 %/)).toBeInTheDocument()
    expect(await screen.findByText('Sin diferencias entre ambas fuentes.')).toBeInTheDocument()
  })

  it('crea una ruta validando antes de enviar', async () => {
    api.crearRuta.mockResolvedValue(ruta({ id: 'r9', codigo: 'NUEVA' }))
    montar('rutas')
    await screen.findByText('Cornelio')
    fireEvent.click(screen.getByRole('button', { name: '+ Nueva ruta' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear ruta' }))
    expect((await within(dialogo).findAllByRole('alert')).length).toBe(2)
    expect(api.crearRuta).not.toHaveBeenCalled()

    const [codigo, nombre] = within(dialogo).getAllByRole('textbox')
    fireEvent.change(codigo, { target: { value: ' nueva ' } })
    fireEvent.change(nombre, { target: { value: 'Ruta Nueva' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear ruta' }))
    await waitFor(() =>
      expect(api.crearRuta).toHaveBeenCalledWith({ codigo: 'nueva', nombre: 'Ruta Nueva', zona: null }),
    )
  })

  it('un rol solo de lectura ve las rutas y el equipo, sin acciones de escritura', async () => {
    sesion.permisos = ['catalogos:leer']
    montar('rutas')
    await screen.findByText('Cornelio')
    expect(screen.getByRole('link', { name: 'Equipo de CORNELIO' })).toHaveAttribute('href', '/catalogos/rutas/r1/equipo')
    expect(screen.queryByRole('button', { name: '+ Nueva ruta' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Desactivar/ })).not.toBeInTheDocument()
  })

  it('muestra el error del servidor al desactivar una ruta en uso', async () => {
    api.desactivarRuta.mockRejectedValue(conCodigo('RUTA_CON_LIQUIDACIONES', { liquidaciones: ['x'] }))
    montar('rutas')
    await screen.findByText('Cornelio')
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar CORNELIO' }))
    expect(await screen.findByText(/Mensaje base \(1 en borrador\)/)).toBeInTheDocument()
  })
})

describe('validarEmpleado / textoErrorEmpleado', () => {
  it('valida el nombre', () => {
    expect(validarEmpleado('A')).toBeTruthy()
    expect(validarEmpleado('  ')).toBeTruthy()
    expect(validarEmpleado('x'.repeat(151))).toBeTruthy()
    expect(validarEmpleado('Ana')).toBeNull()
  })
  it('agrega el detalle de EMPLEADO_EN_USO', () => {
    expect(textoErrorEmpleado(conCodigo('EMPLEADO_EN_USO', { rutas: ['a', 'b'] }))).toContain('rutas: 2')
  })
})

describe('<EmployeesView />', () => {
  it('lista empleados activos e indica el vínculo con un usuario', async () => {
    montar('empleados')
    const ana = (await screen.findByText('Ana')).closest('tr')!
    expect(within(ana).getByText('—')).toBeInTheDocument()
    expect(within(screen.getByText('Beto').closest('tr')!).getByText('Vinculado')).toBeInTheDocument()
    expect(api.listarEmpleados).toHaveBeenCalledWith(expect.objectContaining({ activo: true, offset: 0 }))
  })

  it('crea un empleado con el nombre recortado', async () => {
    api.crearEmpleado.mockResolvedValue({ id: 'e9', nombre_completo: 'Nuevo', activo: true, usuario_id: null, creado_en: '' })
    montar('empleados')
    await screen.findByText('Ana')
    fireEvent.click(screen.getByRole('button', { name: '+ Nuevo empleado' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear empleado' }))
    expect(await within(dialogo).findByRole('alert')).toBeInTheDocument()
    expect(api.crearEmpleado).not.toHaveBeenCalled()
    fireEvent.change(within(dialogo).getByRole('textbox'), { target: { value: '  Nuevo  ' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear empleado' }))
    await waitFor(() => expect(api.crearEmpleado).toHaveBeenCalledWith({ nombre_completo: 'Nuevo' }))
  })

  it('da de baja y muestra el bloqueo si el empleado integra un equipo vigente', async () => {
    api.darDeBajaEmpleado.mockRejectedValue(conCodigo('EMPLEADO_EN_USO', { rutas: ['r1'] }))
    montar('empleados')
    await screen.findByText('Ana')
    fireEvent.click(screen.getByRole('button', { name: 'Dar de baja a Ana' }))
    expect(await screen.findByText(/Mensaje base \(rutas: 1\)/)).toBeInTheDocument()
  })

  it('un rol solo de lectura no ve acciones de escritura', async () => {
    sesion.permisos = ['catalogos:leer']
    montar('empleados')
    await screen.findByText('Ana')
    expect(screen.queryByRole('button', { name: '+ Nuevo empleado' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dar de baja/ })).not.toBeInTheDocument()
  })
})
