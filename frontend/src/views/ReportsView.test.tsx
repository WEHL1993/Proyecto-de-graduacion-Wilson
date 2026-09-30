import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComisionVendedor } from '../types'
import { ReportsView, comisionesPorAgente } from './ReportsView'

// recharts necesita medidas de layout que jsdom no tiene.
vi.mock('recharts', async (original) => {
  const real = await original<typeof import('recharts')>()
  return { ...real, ResponsiveContainer: ({ children }: { children: React.ReactElement }) => <div>{children}</div> }
})

const api = vi.hoisted(() => ({
  obtenerRotacion: vi.fn(),
  obtenerVentasVsProyeccion: vi.fn(),
  obtenerComisiones: vi.fn(),
  descargarConsolidado: vi.fn(),
  listarRutas: vi.fn(),
}))
vi.mock('../services/reportsApi', () => api)
vi.mock('../services/catalogApi', () => ({ listarRutas: api.listarRutas }))

const liq = (o: Partial<ComisionVendedor>): ComisionVendedor => ({
  vendedor_id: 'v1',
  vendedor: 'Cornelio',
  periodo: '2026-03',
  ventas_registradas: 10,
  monto_vendido: '1000.00',
  comision_total: '30.00',
  porcentaje_efectivo: '3.00',
  ...o,
})

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <ReportsView />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listarRutas.mockResolvedValue([{ id: 'r1', codigo: 'R-01', nombre: 'Ruta 1' }])
  api.obtenerVentasVsProyeccion.mockResolvedValue({
    desde: '2026-03-01',
    hasta: '2026-03-30',
    total_real: '350.00',
    total_proyectado: '200.00',
    rutas: [{ ruta_id: 'r1', ruta_codigo: 'R-01', ruta_nombre: 'Ruta 1', real: '350.00', proyectada: '200.00', desviacion_pct: '75.00' }],
    serie: [{ fecha: '2026-03-10', real: '150.00', proyectada: '140.00' }],
  })
  api.obtenerRotacion.mockResolvedValue({
    desde: '2026-03-01',
    hasta: '2026-03-30',
    valor_inventario: '500.00',
    costo_ventas_total: '800.00',
    rotacion_global: '1.6000',
    dias_inventario: '18.8',
    indice_quiebre_global: '50.00',
    rutas: [
      { ruta_id: 'r1', ruta_codigo: 'R-01', ruta_nombre: 'Ruta 1', unidades_vendidas: '350.00', monto_vendido: '1900.00', costo_ventas: '800.00', rotacion: '1.6000', cargas: 1, lineas_carga: 2, lineas_ajustadas: 1, indice_quiebre: '50.00', unidades_no_cubiertas: '10.00' },
    ],
  })
  api.obtenerComisiones.mockResolvedValue({
    periodo_desde: '2026-03',
    periodo_hasta: '2026-03',
    total_vendido: '1000.00',
    total_comisiones: '30.00',
    liquidaciones: [liq({})],
  })
})

describe('comisionesPorAgente', () => {
  it('suma periodos por vendedor y ordena de mayor a menor comisión', () => {
    const r = comisionesPorAgente([
      liq({ periodo: '2026-02', comision_total: '10.00', monto_vendido: '300.00' }),
      liq({ periodo: '2026-03', comision_total: '30.00', monto_vendido: '1000.00' }),
      liq({ vendedor_id: 'v2', vendedor: 'Antonio', comision_total: '55.00', monto_vendido: '1800.00' }),
    ])
    expect(r).toEqual([
      { vendedor: 'Antonio', comision: 55, vendido: 1800 },
      { vendedor: 'Cornelio', comision: 40, vendido: 1300 },
    ])
  })
  it('sin datos devuelve lista vacía', () => expect(comisionesPorAgente([])).toEqual([]))
})

describe('<ReportsView />', () => {
  it('muestra KPIs, periodo resuelto por el servidor y tablas de rotación y comisiones', async () => {
    montar()
    expect(await screen.findByText('Rotación de inventario')).toBeInTheDocument()
    const kpis = screen.getByRole('region', { name: 'Indicadores' })
    await waitFor(() => expect(kpis).toHaveTextContent('1.6×'))
    expect(kpis).toHaveTextContent('Desviación 75 %')
    expect(kpis).toHaveTextContent('50 %')
    expect(await screen.findByText('2026-03-30')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: /rotación y quiebres por ruta/i })).toHaveTextContent('1 / 2')
    expect(screen.getByRole('table', { name: /liquidación de comisiones/i })).toHaveTextContent('Cornelio')
  })

  it('aplicar filtros vuelve a consultar con fechas y ruta', async () => {
    montar()
    await screen.findByText('Rotación de inventario')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-03-05' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-03-20' } })
    fireEvent.change(await screen.findByLabelText('Ruta'), { target: { value: 'r1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
    await waitFor(() =>
      expect(api.obtenerRotacion).toHaveBeenLastCalledWith({ desde: '2026-03-05', hasta: '2026-03-20', rutaId: 'r1' }),
    )
  })

  it('rango invertido bloquea «Aplicar»', async () => {
    montar()
    await screen.findByText('Rotación de inventario')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-04-01' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-03-01' } })
    expect(screen.getByRole('button', { name: 'Aplicar' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('no puede ser posterior')
  })

  it('descarga el consolidado en Excel y CSV con el filtro vigente', async () => {
    api.descargarConsolidado.mockResolvedValue(undefined)
    montar()
    await screen.findByText('Rotación de inventario')
    fireEvent.click(screen.getByRole('button', { name: /excel/i }))
    await waitFor(() => expect(api.descargarConsolidado).toHaveBeenCalledWith({}, 'xlsx'))
    fireEvent.click(screen.getByRole('button', { name: /csv/i }))
    await waitFor(() => expect(api.descargarConsolidado).toHaveBeenLastCalledWith({}, 'csv'))
  })

  it('un fallo de descarga se informa al usuario', async () => {
    api.descargarConsolidado.mockRejectedValue(new Error('Sin conexión'))
    montar()
    await screen.findByText('Rotación de inventario')
    fireEvent.click(screen.getByRole('button', { name: /excel/i }))
    expect(await screen.findByText(/No se pudo descargar el informe: Sin conexión/)).toBeInTheDocument()
  })

  it('sin datos muestra estado vacío en lugar de gráficas', async () => {
    api.obtenerVentasVsProyeccion.mockResolvedValue({ desde: '2026-03-01', hasta: '2026-03-30', total_real: '0', total_proyectado: '0', rutas: [], serie: [] })
    api.obtenerComisiones.mockResolvedValue({ periodo_desde: '2026-03', periodo_hasta: '2026-03', total_vendido: '0', total_comisiones: '0', liquidaciones: [] })
    montar()
    expect((await screen.findAllByText('Sin datos')).length).toBeGreaterThanOrEqual(2)
  })
})
