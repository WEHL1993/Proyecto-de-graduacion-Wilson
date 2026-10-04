import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PERMISOS_VISTA } from '../app/rbac'
import type { PrecargaResponse } from '../types'
import {
  PAGOS_VACIOS,
  diferenciaCaja,
  efectivoEsperado,
  estadoFila,
  semaforoCaja,
  totalesUnidades,
  validar,
  ventaTotal,
} from '../utils/liquidacion'
import type { FilaForm } from '../utils/liquidacion'
import { LiquidacionDiariaView } from './LiquidacionDiariaView'

const permisos = vi.hoisted(() => ({ lista: ['liquidaciones:registrar', 'liquidaciones:cerrar', 'liquidaciones:corregir', 'liquidaciones:leer'] }))
vi.mock('../app/providers/AuthProvider', () => ({
  useAuth: () => ({
    usuario: { id: 'u', nombre_completo: 'Admin', roles: ['Admin'], permisos: permisos.lista },
    can: (p: string) => permisos.lista.includes(p),
    canAny: (ps: readonly string[]) => ps.some((p) => permisos.lista.includes(p)),
  }),
}))

const api = vi.hoisted(() => ({
  listarRutas: vi.fn(),
  precargar: vi.fn(),
  guardarLiquidacion: vi.fn(),
  cerrarLiquidacion: vi.fn(),
  corregirLiquidacion: vi.fn(),
  anularLiquidacion: vi.fn(),
  obtenerConfigLiquidacion: vi.fn(),
}))
vi.mock('../services/catalogApi', () => ({ listarRutas: api.listarRutas }))
vi.mock('../services/liquidacionesApi', () => api)

const fila = (o: Partial<FilaForm> = {}): FilaForm => ({
  producto_id: 'p1',
  sku: '3030-PINA',
  nombre: 'Piña',
  cargada: '20',
  vendida: '15',
  devuelta: '3',
  merma: '2',
  precio: '50',
  agotado: false,
  justificacion: '',
  despachada: null,
  ...o,
})

describe('cálculos de la liquidación', () => {
  it('cuadre de unidades por fila: cuadra, falta o excede', () => {
    expect(estadoFila(fila())).toBe('cuadra')
    expect(estadoFila(fila({ devuelta: '1' }))).toBe('falta')
    expect(estadoFila(fila({ vendida: '19' }))).toBe('excede')
  })

  it('totales y venta calculada (cantidad × precio)', () => {
    const filas = [fila(), fila({ producto_id: 'p2', cargada: '10', vendida: '10', devuelta: '', merma: '', precio: '30' })]
    expect(totalesUnidades(filas)).toEqual({ cargadas: 30, vendidas: 25, devueltas: 3, merma: 2 })
    expect(ventaTotal(filas)).toBe(1050)
  })

  it('efectivo esperado = efectivo + cobro − gastos; diferencia = entregado − esperado', () => {
    const p = { ...PAGOS_VACIOS, efectivo: '800', cobro_saldos: '50', gastos: '20', efectivo_entregado: '800' }
    expect(efectivoEsperado(p)).toBe(830)
    expect(diferenciaCaja(p)).toBe(-30)
  })

  it('semáforo de caja según umbral', () => {
    expect(semaforoCaja(0, 10)).toBe('verde')
    expect(semaforoCaja(-10, 10)).toBe('ambar')
    expect(semaforoCaja(10.01, 10)).toBe('rojo')
  })

  it('valida números negativos o inválidos, exceso y pide justificación si difiere lo despachado', () => {
    const pagos = { ...PAGOS_VACIOS, efectivo: '750', gastos: '-1' }
    const v = validar([fila({ vendida: 'x' }), fila({ producto_id: 'p2', sku: 'B', vendida: '19' })], pagos)
    expect(v.errores.join(' ')).toMatch(/vendida.*número/)
    expect(v.errores.join(' ')).toMatch(/excede/)
    expect(v.errores.join(' ')).toMatch(/gastos/)
    const j = validar([fila({ despachada: 25 })], { ...PAGOS_VACIOS, efectivo: '750' })
    expect(j.errores.join(' ')).toMatch(/justificación/)
    expect(validar([fila({ despachada: 25, justificacion: 'se quedaron' })], { ...PAGOS_VACIOS, efectivo: '750' }).errores).toEqual([])
  })

  it('para cerrar exige cuadrar unidades y dinero', () => {
    expect(validar([fila({ devuelta: '' })], { ...PAGOS_VACIOS, efectivo: '750' }).pendientes.join(' ')).toMatch(/faltan 3/)
    expect(validar([fila()], { ...PAGOS_VACIOS, efectivo: '700' }).pendientes.join(' ')).toMatch(/venta total/)
    expect(validar([fila()], { ...PAGOS_VACIOS, efectivo: '750' })).toEqual({ errores: [], pendientes: [] })
  })

  it('la vista de liquidación solo la habilita el permiso registrar', () => {
    expect(PERMISOS_VISTA.liquidacion).toEqual(['liquidaciones:registrar'])
    expect(PERMISOS_VISTA.liquidaciones).toEqual(['liquidaciones:leer'])
  })
})

const respuesta = (o: object = {}) => ({
  id: 'liq1',
  fecha: '2026-09-01',
  ruta_id: 'r1',
  ruta_nombre: 'Cornelio',
  vendedor_id: 'v1',
  vendedor_nombre: 'Cornelio',
  estado: 'borrador',
  version: 1,
  lote_id: null,
  lineas: [],
  pagos: {},
  advertencias: [],
  ...o,
})

const precarga: PrecargaResponse = {
  fecha: '2026-09-01',
  ruta_id: 'r1',
  carga_id: null,
  liquidacion: null,
  advertencias: ['No hay una carga despachada para la ruta y fecha: ingrese lo cargado manualmente.'],
  lineas: [
    { producto_id: 'p1', sku: '3030-PINA', producto_nombre: 'Piña', cantidad_cargada: '20', precio_unitario: '50' },
    { producto_id: 'p2', sku: '2250-COLA', producto_nombre: 'Cola', cantidad_cargada: '10', precio_unitario: '30' },
  ],
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <LiquidacionDiariaView />
    </QueryClientProvider>,
  )
}
const escribir = (etiqueta: string, valor: string) => fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } })

async function elegirRuta() {
  montar()
  await screen.findByRole('option', { name: /R-01/ })
  fireEvent.change(screen.getByLabelText('Ruta'), { target: { value: 'r1' } })
  await screen.findByText('3030-PINA')
}

beforeEach(() => {
  vi.clearAllMocks()
  permisos.lista = ['liquidaciones:registrar', 'liquidaciones:cerrar', 'liquidaciones:corregir', 'liquidaciones:leer']
  api.listarRutas.mockResolvedValue([{ id: 'r1', codigo: 'R-01', nombre: 'Cornelio' }])
  api.precargar.mockResolvedValue(precarga)
  api.obtenerConfigLiquidacion.mockResolvedValue({ umbral_diferencia_caja: '10.00' })
})

describe('<LiquidacionDiariaView />', () => {
  it('precarga lo cargado, avisa que no hay carga y no deja cerrar con datos vacíos', async () => {
    await elegirRuta()
    expect(screen.getByText(/No hay una carga despachada/)).toBeInTheDocument()
    expect(screen.getByLabelText('Cargado 3030-PINA')).toHaveValue('20')
    expect(screen.getByRole('button', { name: 'Cerrar liquidación' })).toBeDisabled()
    expect(screen.getByTestId('total-cargadas')).toHaveTextContent('30')
  })

  it('muestra cuadres en vivo de unidades y de dinero', async () => {
    await elegirRuta()
    escribir('Vendido 3030-PINA', '15')
    escribir('Devuelto 3030-PINA', '3')
    escribir('Merma 3030-PINA', '2')
    expect(screen.getAllByText(/Cuadra/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('total-vendidas')).toHaveTextContent('15')
    expect(screen.getByText(/Faltan 10/)).toBeInTheDocument() // la fila de cola sin vender

    fireEvent.click(screen.getByRole('button', { name: '2 · Dinero' }))
    expect(screen.getByTestId('venta-total')).toHaveTextContent('750')
    escribir('Efectivo', '700')
    escribir('Cobro de saldos anteriores', '50')
    escribir('Gastos de ruta', '20')
    escribir('Efectivo entregado', '700')
    expect(screen.getByTestId('efectivo-esperado')).toHaveTextContent('730')
    expect(screen.getByTestId('dif-caja')).toHaveTextContent('-30')
    expect(screen.getByTestId('dif-caja').textContent).toMatch(/🔴/) // supera el umbral de Q 10
  })

  it('valida en el cliente: un valor negativo impide guardar el borrador', async () => {
    await elegirRuta()
    escribir('Vendido 3030-PINA', '-1')
    expect(screen.getByRole('button', { name: 'Guardar borrador' })).toBeDisabled()
    expect(screen.getByText(/mayor o igual a 0/)).toBeInTheDocument()
  })

  it('guarda el borrador y envía montos y líneas', async () => {
    api.guardarLiquidacion.mockResolvedValue(respuesta())
    await elegirRuta()
    escribir('Vendido 3030-PINA', '15')
    escribir('Devuelto 3030-PINA', '5')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar borrador' }))
    await waitFor(() => expect(api.guardarLiquidacion).toHaveBeenCalled())
    const cuerpo = api.guardarLiquidacion.mock.calls[0][0]
    expect(cuerpo).toMatchObject({ fecha: expect.any(String), ruta_id: 'r1' })
    expect(cuerpo.lineas[0]).toMatchObject({ producto_id: 'p1', cantidad_cargada: '20', cantidad_vendida: '15', cantidad_devuelta: '5' })
    expect(await screen.findByText(/aún no afecta al modelo/)).toBeInTheDocument()
  })

  it('cerrar pide confirmación que explica que alimenta el modelo y cierra', async () => {
    api.guardarLiquidacion.mockResolvedValue(respuesta())
    api.cerrarLiquidacion.mockResolvedValue(respuesta({ estado: 'cerrada', advertencias: ['La diferencia de caja supera el umbral de Q 10.00.'] }))
    await elegirRuta()
    escribir('Vendido 3030-PINA', '15')
    escribir('Devuelto 3030-PINA', '5')
    escribir('Vendido 2250-COLA', '10')
    fireEvent.click(screen.getByRole('button', { name: '2 · Dinero' }))
    escribir('Efectivo', '1050')
    escribir('Efectivo entregado', '1050')
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar liquidación' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/alimentan el modelo predictivo/)).toBeInTheDocument()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(api.cerrarLiquidacion).toHaveBeenCalledWith('liq1'))
    expect(await screen.findByText(/ya alimentan el modelo/)).toBeInTheDocument()
    expect(screen.getByText(/supera el umbral/)).toBeInTheDocument()
  })

  it('muestra el error de la API (p. ej. un cuadre rechazado por el servidor)', async () => {
    api.guardarLiquidacion.mockRejectedValue(
      new AxiosError('x', '400', undefined, undefined, {
        status: 400,
        data: { codigo: 'UNIDADES_NO_CUADRAN', mensaje: 'Las unidades no cuadran.' },
      } as never),
    )
    await elegirRuta()
    escribir('Vendido 3030-PINA', '15')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar borrador' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Las unidades no cuadran.')
  })

  it('con una liquidación cerrada entra en modo corrección y pide motivo', async () => {
    api.precargar.mockResolvedValue({
      ...precarga,
      liquidacion: respuesta({
        estado: 'cerrada',
        version: 2,
        pagos: { efectivo: '1050', transferencia: '0', credito: '0', cobro_saldos: '0', gastos: '0', efectivo_entregado: '1050' },
        lineas: [
          { producto_id: 'p1', sku: '3030-PINA', producto_nombre: 'Piña', cantidad_cargada: '20', cantidad_vendida: '15', cantidad_devuelta: '5', cantidad_merma: '0', precio_unitario: '50', monto_total: '750', agotado: false },
          { producto_id: 'p2', sku: '2250-COLA', producto_nombre: 'Cola', cantidad_cargada: '10', cantidad_vendida: '10', cantidad_devuelta: '0', cantidad_merma: '0', precio_unitario: '30', monto_total: '300', agotado: false },
        ],
      }),
    })
    api.corregirLiquidacion.mockResolvedValue(respuesta({ estado: 'cerrada', version: 3 }))
    await elegirRuta()
    expect(await screen.findByText(/Corrección · v2/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar borrador' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Corregir liquidación' }))
    const dialogo = await screen.findByRole('dialog')
    const confirmar = within(dialogo).getByRole('button', { name: 'Confirmar' })
    expect(confirmar).toBeDisabled()
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'conteo equivocado' } })
    fireEvent.click(confirmar)
    await waitFor(() => expect(api.corregirLiquidacion).toHaveBeenCalledWith('liq1', expect.any(Object), 'conteo equivocado'))
  })

  it('oculta guardar y cerrar sin los permisos correspondientes', async () => {
    permisos.lista = ['liquidaciones:registrar']
    await elegirRuta()
    expect(screen.getByRole('button', { name: 'Guardar borrador' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cerrar liquidación' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anular' })).not.toBeInTheDocument()
  })
})
