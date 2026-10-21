import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SalesDashboardView } from './SalesDashboardView'

vi.mock('../app/providers/AuthProvider', () => ({
  useAuth: () => ({
    can: (p: string) => ['carga_ruta:aprobar', 'carga_ruta:generar'].includes(p),
    canAny: () => true,
  }),
}))

const item = (o: object) => ({
  producto_id: 'p1',
  sku: 'BEB-0034',
  producto_nombre: 'Gaseosa 2L',
  cantidad_predicha: '10',
  stock_disponible: '100',
  cantidad_sugerida: '10',
  cantidad_aprobada: null,
  ajustado_por_stock: false,
  ...o,
})

const hooks = vi.hoisted(() => ({ plan: { data: null as unknown, isPending: false, isError: false, isSuccess: true } }))
vi.mock('../hooks/useLoadPlan', () => ({
  useLoadPlan: () => hooks.plan,
  useLoadPlanActions: () => ({ mutacion: { isPending: false, mutate: vi.fn() }, recalcular: { isPending: false, mutate: vi.fn() } }),
}))
vi.mock('../hooks/useDemandForecast', () => ({ useDemandForecast: () => ({ data: undefined }) }))
vi.mock('../hooks/useModelMetrics', () => ({ useModelMetrics: () => ({ data: undefined }) }))
vi.mock('../components/charts/DemandChart', () => ({ DemandChart: () => null }))
vi.mock('../services/catalogApi', () => ({ listarRutas: vi.fn().mockResolvedValue([{ id: 'r1', codigo: 'R-01', nombre: 'Cornelio' }]) }))

beforeEach(() => {
  hooks.plan.data = {
    carga_id: 'c1',
    estado: 'borrador',
    items: [item({}), item({ producto_id: 'p2', sku: 'LIM-0003', cantidad_sugerida: '0', cantidad_predicha: '0' })],
  }
})

async function abrirPlan() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={cliente}>
      <SalesDashboardView />
    </QueryClientProvider>,
  )
  await screen.findByRole('option', { name: /R-01/ })
  fireEvent.click(screen.getByRole('button', { name: 'Consultar' }))
  await screen.findByLabelText('Incluir BEB-0034')
}

describe('<SalesDashboardView /> · casilla Incluir', () => {
  it('escribir una cantidad mayor que 0 marca la fila sola', async () => {
    await abrirPlan()
    const casilla = screen.getByLabelText('Incluir LIM-0003') as HTMLInputElement
    expect(casilla.checked).toBe(false)

    fireEvent.change(screen.getByLabelText('Cantidad aprobada de LIM-0003'), { target: { value: '10' } })
    expect(casilla.checked).toBe(true)
  })

  it('dejar la cantidad en 0 no marca la fila ni desmarca una marcada', async () => {
    await abrirPlan()
    const vacia = screen.getByLabelText('Incluir LIM-0003') as HTMLInputElement
    fireEvent.change(screen.getByLabelText('Cantidad aprobada de LIM-0003'), { target: { value: '0' } })
    expect(vacia.checked).toBe(false)

    const marcada = screen.getByLabelText('Incluir BEB-0034') as HTMLInputElement
    expect(marcada.checked).toBe(true)
    fireEvent.change(screen.getByLabelText('Cantidad aprobada de BEB-0034'), { target: { value: '0' } })
    expect(marcada.checked).toBe(true)
  })
})
