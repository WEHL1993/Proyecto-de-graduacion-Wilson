import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ReceptionView, cantidadRecibidaValida, importeLinea, precioUnitarioValido } from './ReceptionView'
import * as api from '../services/purchasingApi'

vi.mock('../services/purchasingApi', () => ({
  pedidosPendientes: vi.fn(), productosRecepcion: vi.fn(), registrarRecepcion: vi.fn(),
}))
const pedido = { id: 'p1', fecha_pedido: '2026-10-20', items: [
  { producto_id: 'a', sku: 'A', producto_nombre: 'Pan', cantidad: '10', costo_unitario: '30.0000' },
  { producto_id: 'b', sku: 'B', producto_nombre: 'Galletas', cantidad: '5', costo_unitario: '50.0000' },
] }
const factura = {
  serie: '1FEF6CC7', numero: '1265782595', fecha_emision: '2026-10-20', condicion_pago: null,
}
function llenarFactura() {
  for (const [etiqueta, valor] of [
    ['Serie FEL', factura.serie], ['Número FEL', factura.numero],
    ['Fecha de emisión', factura.fecha_emision],
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
  vi.mocked(api.productosRecepcion).mockResolvedValue([{ id: 'a', sku: 'A', nombre: 'Pan', costo_unitario: '30.0000' }] as never)
  vi.mocked(api.registrarRecepcion).mockResolvedValue({ estado_pedido: 'recibido_parcial' } as never)
})
describe('cantidadRecibidaValida', () => {
  it('acepta cero y dos decimales; rechaza negativos, exceso y datos incompletos', () => {
    for (const v of ['0', '1', '12.50']) expect(cantidadRecibidaValida(v)).toBe(true)
    for (const v of ['', '-1', '1.234', 'abc', '10000000000']) expect(cantidadRecibidaValida(v)).toBe(false)
  })
})
describe('importeLinea', () => {
  it('multiplica cantidad por precio y no calcula con datos incompletos o inválidos', () => {
    expect(importeLinea('210', '30')).toBe(6300)
    expect(importeLinea('10.5', '2.3333')).toBe(24.5)
    for (const [c, p] of [['', '30'], ['10', ''], ['10', 'abc'], ['-1', '5']]) expect(importeLinea(c, p)).toBeNull()
    expect(precioUnitarioValido('')).toBe(true)
    expect(precioUnitarioValido('1.23456')).toBe(false)
  })
})
describe('ReceptionView', () => {
  it('muestra código, descripción, precio, importe bruto y subtotal sin columna de descuento', async () => {
    montar('/recepcion?pedido=p1')
    await screen.findAllByRole('spinbutton')
    for (const t of ['Código', 'Descripción', 'Cantidad', 'Precio unitario', 'Importe bruto', 'Subtotal'])
      expect(screen.getByRole('columnheader', { name: t })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /Descuento/ })).toBeNull()
    expect((screen.getByLabelText(/Precio unitario de A/) as HTMLInputElement).value).toBe('30')
  })
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
        { producto_id: 'a', cantidad_recibida: '8', precio_unitario: '30', observacion: 'Faltan dos' },
        { producto_id: 'b', cantidad_recibida: '0', precio_unitario: '50', observacion: '' },
      ],
    })
    expect(await screen.findByText(/registrada con diferencias/)).toBeInTheDocument()
  })
  it('agrega productos sin pedido y conserva los datos cuando falla el guardado', async () => {
    vi.mocked(api.registrarRecepcion).mockRejectedValue(new Error('Fallo de red'))
    montar()
    // Por defecto hay una sola fila vacía; no hay cantidades hasta elegir un producto.
    await screen.findByRole('option', { name: /Pan/, hidden: true }) // productos cargados
    const codigo = screen.getByLabelText('Código del producto')
    expect(screen.queryByRole('spinbutton')).toBeNull()
    fireEvent.change(codigo, { target: { value: 'pa' } })
    expect(screen.queryByRole('spinbutton')).toBeNull()
    fireEvent.change(codigo, { target: { value: 'a' } })
    expect(screen.getByLabelText('Código del producto')).toHaveValue('')
    expect(screen.getByRole('spinbutton')).toHaveFocus()
    expect(screen.getByLabelText(/Precio unitario de A/)).toHaveValue('30')
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '3' } })
    llenarFactura()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar recepción' }))
    await waitFor(() => expect(api.registrarRecepcion).toHaveBeenCalled())
    expect(vi.mocked(api.registrarRecepcion).mock.calls[0][0].pedido_id).toBeNull()
    expect(screen.getByRole('spinbutton')).toHaveValue(3)
  })
  it('agrega el producto al escribir su nombre y no lo ofrece dos veces', async () => {
    montar()
    await screen.findByRole('option', { name: /Pan/, hidden: true }) // productos cargados
    fireEvent.change(screen.getByLabelText('Descripción del producto'), { target: { value: 'pan' } })
    expect(screen.getByRole('spinbutton')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Código del producto'), { target: { value: 'A' } })
    expect(screen.getAllByRole('spinbutton')).toHaveLength(1)
  })
  it('permite reintentar la carga', async () => {
    vi.mocked(api.pedidosPendientes).mockRejectedValue(new Error('Sin conexion'))
    montar()
    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
  it('exige los tres campos obligatorios', async () => {
    montar('/recepcion?pedido=p1')
    await screen.findAllByRole('spinbutton')
    llenarFactura()
    const boton = screen.getByRole('button', { name: 'Guardar recepción' })
    expect(boton).toBeEnabled()
    for (const etiqueta of ['Serie FEL', 'Número FEL', 'Fecha de emisión']) {
      const input = screen.getByLabelText(new RegExp(etiqueta))
      fireEvent.change(input, { target: { value: '' } })
      expect(boton).toBeDisabled()
      llenarFactura()
    }
    expect(api.registrarRecepcion).not.toHaveBeenCalled()
  })
  it('envía la condición de pago y muestra FACTURA_DUPLICADA sin borrar el formulario', async () => {
    const mensaje = 'La factura ya fue registrada: el UUID de autorización o la serie y número están duplicados.'
    vi.mocked(api.registrarRecepcion).mockRejectedValue({
      isAxiosError: true, response: { status: 409, data: { codigo: 'FACTURA_DUPLICADA', mensaje } },
    })
    montar('/recepcion?pedido=p1')
    await screen.findAllByRole('spinbutton')
    llenarFactura()
    fireEvent.change(screen.getByLabelText(/Condición de pago/), { target: { value: 'Crédito a 3 días' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar recepción' }))
    expect(await screen.findByText(mensaje)).toBeInTheDocument()
    expect(screen.getByLabelText('Serie FEL')).toHaveValue(factura.serie)
    expect(vi.mocked(api.registrarRecepcion).mock.calls[0][0]).toMatchObject({
      ...factura, condicion_pago: 'Crédito a 3 días',
    })
    expect(screen.queryByLabelText(/UUID|Serie admin|Número admin/)).toBeNull()
  })
})
