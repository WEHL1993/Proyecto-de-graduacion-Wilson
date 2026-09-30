import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AlertBanner, FranjaAlertasCriticas } from './AlertBanner'

const permisos = vi.hoisted(() => ({ actuales: ['alertas:leer', 'inventario:leer'] as string[] }))
vi.mock('../../app/providers/AuthProvider', () => ({
  useAuth: () => ({
    can: (p: string) => permisos.actuales.includes(p),
    canAny: (ps: readonly string[]) => ps.some((p) => permisos.actuales.includes(p)),
  }),
}))

const api = vi.hoisted(() => ({ listarAlertas: vi.fn(), reconocerAlerta: vi.fn() }))
vi.mock('../../services/catalogApi', () => api)

const alerta = (o: object) => ({
  id: 'a1',
  tipo: 'stock_bajo',
  severidad: 'advertencia',
  mensaje: 'Stock bajo en Producto A',
  estado: 'abierta',
  creada_en: '2026-03-01T00:00:00Z',
  ...o,
})

function montar(ui: React.ReactElement) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  permisos.actuales = ['alertas:leer', 'inventario:leer']
  api.listarAlertas.mockResolvedValue({
    total: 2,
    alertas: [alerta({ id: 'a1', severidad: 'critica', mensaje: 'Quiebre en Producto B', tipo: 'quiebre_proyectado' }), alerta({ id: 'a2' })],
  })
})

describe('<AlertBanner />', () => {
  it('sin permiso alertas:leer no renderiza nada ni consulta', () => {
    permisos.actuales = ['inventario:leer']
    const { container } = montar(<AlertBanner />)
    expect(container).toBeEmptyDOMElement()
    expect(api.listarAlertas).not.toHaveBeenCalled()
  })

  it('muestra el contador con críticas y lista las alertas al abrir', async () => {
    montar(<AlertBanner />)
    const boton = await screen.findByRole('button', { name: /2 alertas/ })
    expect(boton).toHaveTextContent('(1 crítica)')
    fireEvent.click(boton)
    expect(screen.getByText('Quiebre en Producto B')).toBeInTheDocument()
    expect(screen.getByText('Stock bajo en Producto A')).toBeInTheDocument()
  })

  it('«Ir a resolver» solo aparece si el rol puede abrir la vista destino', async () => {
    montar(<AlertBanner />)
    fireEvent.click(await screen.findByRole('button', { name: /2 alertas/ }))
    // stock_bajo → /inventario (permitido); quiebre_proyectado → /compras (sin permiso).
    expect(screen.getAllByRole('link', { name: 'Ir a resolver' })).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Ir a resolver' })).toHaveAttribute('href', '/inventario')
  })

  it('reconocer llama a la API y recarga la bandeja', async () => {
    api.reconocerAlerta.mockResolvedValue(alerta({ estado: 'reconocida' }))
    montar(<AlertBanner />)
    fireEvent.click(await screen.findByRole('button', { name: /2 alertas/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Reconocer alerta: Stock bajo' }))
    await waitFor(() => expect(api.reconocerAlerta).toHaveBeenCalledWith('a2'))
    await waitFor(() => expect(api.listarAlertas.mock.calls.length).toBeGreaterThan(1))
  })

  it('sin alertas lo indica', async () => {
    api.listarAlertas.mockResolvedValue({ total: 0, alertas: [] })
    montar(<AlertBanner />)
    fireEvent.click(await screen.findByRole('button', { name: /0 alertas/ }))
    expect(screen.getByText('Sin alertas abiertas.')).toBeInTheDocument()
  })
})

describe('<FranjaAlertasCriticas />', () => {
  it('avisa con la primera alerta crítica', async () => {
    montar(<FranjaAlertasCriticas />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Alerta crítica: Quiebre en Producto B')
  })
  it('no aparece si no hay críticas', async () => {
    api.listarAlertas.mockResolvedValue({ total: 1, alertas: [alerta({})] })
    montar(<FranjaAlertasCriticas />)
    await waitFor(() => expect(api.listarAlertas).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
