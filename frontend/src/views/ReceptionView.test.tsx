import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ReceptionView, cantidadRecibidaValida, uuidAutorizacionValido } from './ReceptionView'
import * as api from '../services/purchasingApi'

vi.mock('../services/purchasingApi', () => ({
  pedidosPendientes: vi.fn(), productosRecepcion: vi.fn(), registrarRecepcion: vi.fn(),
}))
const pedido = { id: 'p1', fecha_pedido: '2026-10-20', items: [
  { producto_id: 'a', sku: 'A', producto_nombre: 'Pan', cantidad: '10' },
  { producto_id: 'b', sku: 'B', producto_nombre: 'Galletas', cantidad: '5' },
] }
const factura = {
  serie: '1FEF6CC7', numero: '1265782595',
  numero_autorizacion: '1FEF6CC7-4B72-4F43-A218-C10D0D12CE48', fecha_emision: '2026-10-20',
  condicion_pago: null, serie_admin: null, numero_admin: null,
}
function llenarFactura() {
  for (const [etiqueta, valor] of [
    ['Serie FEL', factura.serie], ['Número FEL', factura.numero],
    ['UUID de autorización', factura.numero_autorizacion], ['Fecha de emisión', factura.fecha_emision],
  ]) fireEvent.change(screen.getByLabelText(new RegExp(etiqueta)), { target: { value: valor } })
}
function montar(url = '/recepcion') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>
    <ReceptionView />
  </MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.pedidosPendientes).mockResolvedValue([pedido] as never)
  vi.mocked(api.productosRecepcion).mockResolvedValue([{ id: 'a', sku: 'A', nombre: 'Pan' }] as never)
  vi.mocked(api.registrarRecepcion).mockResolvedValue({ estado_pedido: 'recibido_parcial' } as never)
})
describe('cantidadRecibidaValida', () => {
  it('acepta cero y dos decimales; rechaza negativos, exceso y datos incompletos', () => {
    for (const v of ['0', '1', '12.50']) expect(cantidadRecibidaValida(v)).toBe(true)
    for (const v of ['', '-1', '1.234', 'abc', '10000000000']) expect(cantidadRecibidaValida(v)).toBe(false)
  })
})
describe('uuidAutorizacionValido', () => {
  it('acepta UUID con guiones en ambas cajas y rechaza formatos incompletos', () => {
    expect(uuidAutorizacionValido(factura.numero_autorizacion)).toBe(true)
    expect(uuidAutorizacionValido(factura.numero_autorizacion.toLowerCase())).toBe(true)
    for (const v of ['', 'abc', factura.numero_autorizacion.replaceAll('-', ''),
      'ZFEF6CC7-4B72-4F43-A218-C10D0D12CE48']) expect(uuidAutorizacionValido(v)).toBe(false)
  })
})
describe('ReceptionView', () => {
  it('exige documento y guarda las cantidades reales, incluido cero y observaciones', async () => {
    montar('/recepcion?pedido=p1')
    const cantidades = await screen.findAllByRole('spinbutton')
    expect(screen.getByRole('button', { name: 'Guardar recepción' })).toBeDisabled()
    llenarFactura()
    fireEvent.change(cantidades[0], { target: { value: '8' } })
    fireEvent.change(cantidades[1], { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText(/Observación de A/), { target: { value: 'Faltan dos' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar recepción' }))
    await waitFor(() => expect(api.registrarRecepcion).toHaveBeenCalled())
    expect(vi.mocked(api.registrarRecepcion).mock.calls[0][0]).toEqual({
      pedido_id: 'p1', ...factura, items: [
        { producto_id: 'a', cantidad_recibida: '8', observacion: 'Faltan dos' },
        { producto_id: 'b', cantidad_recibida: '0', observacion: '' },
      ],
    })
    expect(await screen.findByText(/registrada con diferencias/)).toBeInTheDocument()
  })
  it('agrega productos sin pedido y conserva los datos cuando falla el guardado', async () => {
    vi.mocked(api.registrarRecepcion).mockRejectedValue(new Error('Fallo de red'))
    montar()
    await screen.findByRole('option', { name: /Pan/ })
    fireEvent.change(screen.getByLabelText('Producto'), { target: { value: 'a' } })
    fireEvent.click(screen.getByRole('button', { name: 'Agregar producto' }))
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '3' } })
    llenarFactura()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar recepción' }))
    await waitFor(() => expect(api.registrarRecepcion).toHaveBeenCalled())
    expect(vi.mocked(api.registrarRecepcion).mock.calls[0][0].pedido_id).toBeNull()
    expect(screen.getByRole('spinbutton')).toHaveValue(3)
  })
  it('permite reintentar la carga', async () => {
    vi.mocked(api.pedidosPendientes).mockRejectedValue(new Error('Sin conexion'))
    montar()
    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
  it('bloquea UUID inválido y exige los cuatro campos obligatorios', async () => {
    montar('/recepcion?pedido=p1')
    await screen.findAllByRole('spinbutton')
    llenarFactura()
    const boton = screen.getByRole('button', { name: 'Guardar recepción' })
    expect(boton).toBeEnabled()
    for (const etiqueta of ['Serie FEL', 'Número FEL', 'UUID de autorización', 'Fecha de emisión']) {
      const input = screen.getByLabelText(new RegExp(etiqueta))
      fireEvent.change(input, { target: { value: '' } })
      expect(boton).toBeDisabled()
      llenarFactura()
    }
    fireEvent.change(screen.getByLabelText(/UUID de autorización/), { target: { value: 'incorrecto' } })
    expect(boton).toBeDisabled()
    expect(screen.getByText(/Ingrese un UUID válido/)).toBeInTheDocument()
    expect(api.registrarRecepcion).not.toHaveBeenCalled()
  })
  it('envía los opcionales y muestra FACTURA_DUPLICADA sin borrar el formulario', async () => {
    const mensaje = 'La factura ya fue registrada: el UUID de autorización o la serie y número están duplicados.'
    vi.mocked(api.registrarRecepcion).mockRejectedValue({
      isAxiosError: true, response: { status: 409, data: { codigo: 'FACTURA_DUPLICADA', mensaje } },
    })
    montar('/recepcion?pedido=p1')
    await screen.findAllByRole('spinbutton')
    llenarFactura()
    for (const [etiqueta, valor] of [
      ['Condición de pago', 'Crédito a 3 días'], ['Serie admin', 'FEL14'], ['Número admin', '77058'],
    ]) fireEvent.change(screen.getByLabelText(new RegExp(etiqueta)), { target: { value: valor } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar recepción' }))
    expect(await screen.findByText(mensaje)).toBeInTheDocument()
    expect(screen.getByLabelText('Serie FEL')).toHaveValue(factura.serie)
    expect(vi.mocked(api.registrarRecepcion).mock.calls[0][0]).toMatchObject({
      ...factura, condicion_pago: 'Crédito a 3 días', serie_admin: 'FEL14', numero_admin: '77058',
    })
  })
})
