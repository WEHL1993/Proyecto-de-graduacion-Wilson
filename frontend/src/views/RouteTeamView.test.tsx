import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EquipoRutaOut } from '../types'
import { aCentavos, FILA_VACIA, RouteTeamView, sumaCentavos, textoSuma, validarEquipo } from './RouteTeamView'
import type { FilaEquipo } from './RouteTeamView'

const sesion = vi.hoisted(() => ({ permisos: [] as string[] }))
vi.mock('../app/providers/AuthProvider', () => ({
  useAuth: () => ({
    usuario: { id: 'yo', nombre_completo: 'Admin', roles: [], permisos: sesion.permisos },
    can: (p: string) => sesion.permisos.includes(p),
    canAny: (ps: readonly string[]) => ps.some((p) => sesion.permisos.includes(p)),
  }),
}))

const api = vi.hoisted(() => ({
  obtenerRuta: vi.fn(),
  obtenerEquipo: vi.fn(),
  listarEmpleados: vi.fn(),
  reemplazarEquipo: vi.fn(),
}))
vi.mock('../services/routesAdminApi', () => api)

const fila = (empleado_id: string, rol_en_ruta: FilaEquipo['rol_en_ruta'], porcentaje: string): FilaEquipo => ({
  empleado_id,
  rol_en_ruta,
  porcentaje,
})

describe('aCentavos / sumaCentavos', () => {
  it('convierte porcentajes sin errores de coma flotante', () => {
    expect(aCentavos('33.33')).toBe(3333)
    expect(aCentavos('33,34')).toBe(3334)
    expect(aCentavos('0.1')).toBe(10)
    expect(aCentavos('100')).toBe(10000)
  })
  it('rechaza formatos no válidos', () => {
    for (const malo of ['', 'abc', '-1', '1.234', '1e2']) expect(aCentavos(malo)).toBeNull()
  })
  it('suma exacta: 33,33 + 33,33 + 33,34 = 100,00', () => {
    const filas = [fila('a', 'vendedor', '33.33'), fila('b', 'chofer', '33.33'), fila('c', 'auxiliar', '33.34')]
    expect(sumaCentavos(filas)).toBe(10000)
    expect(textoSuma(sumaCentavos(filas))).toBe('100.00')
  })
})

describe('validarEquipo', () => {
  const valido = [fila('a', 'vendedor', '60'), fila('b', 'chofer', '40')]
  it('acepta un equipo que suma 100', () => expect(validarEquipo(valido)).toEqual([]))
  it('acepta un equipo sin vendedor (el servidor lo permite)', () => {
    expect(validarEquipo([fila('a', 'chofer', '50'), fila('b', 'auxiliar', '50')])).toEqual([])
  })
  it('rechaza una suma distinta de 100,00 e indica cuánto suma', () => {
    const e = validarEquipo([fila('a', 'vendedor', '60'), fila('b', 'chofer', '39.99')])
    expect(e.join(' ')).toMatch(/suman 99\.99/)
  })
  it('rechaza equipo vacío, filas sin empleado, repetidos y dos vendedores', () => {
    expect(validarEquipo([])).toHaveLength(1)
    expect(validarEquipo([FILA_VACIA, fila('b', 'vendedor', '100')]).join(' ')).toMatch(/Seleccione un empleado/)
    expect(validarEquipo([fila('a', 'chofer', '50'), fila('a', 'auxiliar', '50')]).join(' ')).toMatch(/repetirse/)
    expect(validarEquipo([fila('a', 'vendedor', '50'), fila('b', 'vendedor', '50')]).join(' ')).toMatch(/un vendedor/)
  })
  it('rechaza porcentajes inválidos', () => {
    expect(validarEquipo([fila('a', 'vendedor', 'abc')]).join(' ')).toMatch(/número entre 0 y 100/)
    expect(validarEquipo([fila('a', 'vendedor', '101')]).join(' ')).toMatch(/superar 100/)
  })
})

const EQUIPO: EquipoRutaOut = {
  ruta_id: 'r1',
  integrantes: [
    { empleado_id: 'e1', nombre_completo: 'Ana', rol_en_ruta: 'vendedor', porcentaje_reparto: '60.00', vigente_desde: '2026-10-01', vigente_hasta: null },
    { empleado_id: 'e2', nombre_completo: 'Beto', rol_en_ruta: 'chofer', porcentaje_reparto: '40.00', vigente_desde: '2026-10-01', vigente_hasta: null },
  ],
  suma_porcentaje: '100.00',
  suma_100: true,
  tiene_vendedor: true,
  historial: [
    { empleado_id: 'e3', nombre_completo: 'Carla', rol_en_ruta: 'vendedor', porcentaje_reparto: '100.00', vigente_desde: '2026-01-01', vigente_hasta: '2026-09-30' },
  ],
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={['/catalogos/rutas/r1/equipo']}>
        <Routes>
          <Route path="/catalogos/rutas/:rutaId/equipo" element={<RouteTeamView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  sesion.permisos = ['catalogos:leer', 'catalogos:gestionar']
  api.obtenerRuta.mockResolvedValue({ id: 'r1', codigo: 'CORNELIO', nombre: 'Cornelio' })
  api.obtenerEquipo.mockResolvedValue(EQUIPO)
  api.listarEmpleados.mockResolvedValue({
    items: [
      { id: 'e1', nombre_completo: 'Ana', activo: true, usuario_id: null, creado_en: '' },
      { id: 'e2', nombre_completo: 'Beto', activo: true, usuario_id: null, creado_en: '' },
      { id: 'e4', nombre_completo: 'Dario', activo: true, usuario_id: null, creado_en: '' },
    ],
    total: 3,
    limit: 200,
    offset: 0,
  })
})

describe('<RouteTeamView />', () => {
  it('muestra el equipo vigente, el indicador en verde y el historial', async () => {
    montar()
    expect(await screen.findByText(/Suma de reparto/)).toHaveAttribute('data-suma-100', 'si')
    expect(screen.getByText(/Suma de reparto: 100.00 %/)).toBeInTheDocument()
    expect(screen.getByLabelText('Porcentaje 1')).toHaveValue('60.00')
    expect(screen.getByText('Carla')).toBeInTheDocument()
    expect(screen.getByText(/2026-01-01 → 2026-09-30/)).toBeInTheDocument()
  })

  it('el indicador pasa a rojo y no guarda si el reparto no suma 100', async () => {
    montar()
    await screen.findByLabelText('Porcentaje 1')
    fireEvent.change(screen.getByLabelText('Porcentaje 2'), { target: { value: '35' } })
    expect(screen.getByText(/Suma de reparto/)).toHaveAttribute('data-suma-100', 'no')
    expect(screen.getByText(/Suma de reparto/)).toHaveTextContent('faltan 5.00')

    fireEvent.click(screen.getByRole('button', { name: 'Guardar equipo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/suman 95\.00/)
    expect(api.reemplazarEquipo).not.toHaveBeenCalled()
  })

  it('guarda el equipo con porcentajes de dos decimales y la vigencia indicada', async () => {
    api.reemplazarEquipo.mockResolvedValue(EQUIPO)
    montar()
    await screen.findByLabelText('Porcentaje 1')
    fireEvent.change(screen.getByLabelText('Porcentaje 1'), { target: { value: '55,5' } })
    fireEvent.change(screen.getByLabelText('Porcentaje 2'), { target: { value: '44.5' } })
    fireEvent.change(screen.getByLabelText('Vigente desde'), { target: { value: '2026-11-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar equipo' }))

    await waitFor(() => expect(api.reemplazarEquipo).toHaveBeenCalledTimes(1))
    expect(api.reemplazarEquipo).toHaveBeenCalledWith('r1', {
      vigente_desde: '2026-11-01',
      integrantes: [
        { empleado_id: 'e1', rol_en_ruta: 'vendedor', porcentaje_reparto: '55.50' },
        { empleado_id: 'e2', rol_en_ruta: 'chofer', porcentaje_reparto: '44.50' },
      ],
    })
  })

  it('muestra el error del servidor (el servidor es la autoridad)', async () => {
    api.reemplazarEquipo.mockRejectedValue({
      isAxiosError: true,
      response: { status: 400, data: { codigo: 'EQUIPO_NO_SUMA_100', mensaje: 'Los porcentajes deben sumar 100,00.' } },
    })
    montar()
    await screen.findByLabelText('Porcentaje 1')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar equipo' }))
    expect(await screen.findByText(/deben sumar 100,00/)).toBeInTheDocument()
  })

  it('agrega y quita integrantes', async () => {
    montar()
    await screen.findByLabelText('Porcentaje 1')
    fireEvent.click(screen.getByRole('button', { name: '+ Agregar integrante' }))
    expect(screen.getByLabelText('Empleado 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar fila 3' }))
    expect(screen.queryByLabelText('Empleado 3')).not.toBeInTheDocument()
  })

  it('un rol solo de lectura ve el equipo pero no puede editarlo', async () => {
    sesion.permisos = ['catalogos:leer']
    montar()
    await screen.findByLabelText('Porcentaje 1')
    expect(screen.getByLabelText('Porcentaje 1')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guardar equipo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Agregar integrante' })).not.toBeInTheDocument()
  })
})
