import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LiquidacionesHistorialView } from './LiquidacionesHistorialView'

const api = vi.hoisted(() => ({ listarRutas: vi.fn(), listarLiquidaciones: vi.fn(), obtenerLiquidacion: vi.fn() }))
vi.mock('../services/catalogApi', () => ({ listarRutas: api.listarRutas }))
vi.mock('../services/liquidacionesApi', () => api)

const liq = {
  id: 'l1',
  fecha: '2026-09-01',
  ruta_id: 'r1',
  ruta_nombre: 'Cornelio',
  vendedor_id: 'v1',
  vendedor_nombre: 'Cornelio Pérez',
  estado: 'cerrada',
  version: 2,
  unidades_vendidas: '25',
  venta_total: '1050',
  diferencia_caja: '-30',
  cerrado_en: '2026-09-01T20:00:00Z',
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <LiquidacionesHistorialView />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listarRutas.mockResolvedValue([{ id: 'r1', codigo: 'R-01', nombre: 'Cornelio' }])
  api.listarLiquidaciones.mockResolvedValue({ total: 1, liquidaciones: [liq] })
})

describe('<LiquidacionesHistorialView />', () => {
  it('lista liquidaciones con estado, versión y diferencia de caja', async () => {
    montar()
    expect(await screen.findByText('Cornelio Pérez')).toBeInTheDocument()
    expect(screen.getByText(/cerrada · v2/)).toBeInTheDocument()
    expect(screen.getByText('Q -30')).toBeInTheDocument()
  })

  it('filtra por estado y vuelve a consultar con el filtro', async () => {
    montar()
    await screen.findByText('Cornelio Pérez')
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'anulada' } })
    await waitFor(() => expect(api.listarLiquidaciones).toHaveBeenLastCalledWith(expect.objectContaining({ estado: 'anulada', offset: 0 })))
  })

  it('abre el detalle con el cuadre de caja', async () => {
    api.obtenerLiquidacion.mockResolvedValue({
      ...liq,
      lineas: [{ producto_id: 'p1', sku: '3030-PINA', cantidad_cargada: '20', cantidad_vendida: '15', cantidad_devuelta: '3', cantidad_merma: '2', monto_total: '750', agotado: true }],
      cuadre_dinero: { venta_total: '1050', efectivo_esperado: '830', efectivo_entregado: '800', diferencia_caja: '-30', supera_umbral: true },
      devolucion_esperada: '3',
    })
    montar()
    fireEvent.click(await screen.findByRole('button', { name: /Ver detalle/ }))
    expect(await screen.findByText('Efectivo esperado')).toBeInTheDocument()
    expect(screen.getByText('3030-PINA')).toBeInTheDocument()
  })

  it('informa cuando no hay liquidaciones y muestra errores de la API', async () => {
    api.listarLiquidaciones.mockResolvedValue({ total: 0, liquidaciones: [] })
    montar()
    expect(await screen.findByText('Sin liquidaciones')).toBeInTheDocument()
  })
})
