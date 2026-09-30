import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { SugerenciaCompra } from '../types'
import { Progreso, agruparPorProveedor, cantidadValida } from './PurchasingView'
import { alertasStockBajo } from './InventoryView'

const sug = (o: Partial<SugerenciaCompra>): SugerenciaCompra => ({
  producto_id: 'p1',
  sku: 'A',
  nombre: 'Prod A',
  proveedor_id: 'v1',
  proveedor_nombre: 'Proveedor 1',
  lead_time_dias: 3,
  stock_actual: '20',
  stock_minimo: '30',
  demanda_proyectada: '70',
  cantidad_sugerida: '80',
  costo_unitario: '2.50',
  pronostico_disponible: true,
  ...o,
})

describe('agruparPorProveedor', () => {
  it('una orden por proveedor, conservando el lead time', () => {
    const grupos = agruparPorProveedor([
      sug({}),
      sug({ producto_id: 'p2', sku: 'B' }),
      sug({ producto_id: 'p3', proveedor_id: 'v2', proveedor_nombre: 'Proveedor 2', lead_time_dias: 7 }),
    ])
    expect(grupos.map((g) => [g.nombre, g.leadTimeDias, g.filas.length])).toEqual([
      ['Proveedor 1', 3, 2],
      ['Proveedor 2', 7, 1],
    ])
  })
})

describe('cantidadValida', () => {
  it('acepta positivos con hasta 2 decimales', () => {
    expect(cantidadValida('80')).toBe(true)
    expect(cantidadValida('10.5')).toBe(true)
  })
  it('rechaza vacío, cero, negativos, texto y más de 2 decimales', () => {
    for (const v of ['', '0', '0.00', '-1', 'abc', '1.234']) expect(cantidadValida(v)).toBe(false)
  })
})

describe('<Progreso />', () => {
  it('marca la etapa actual y las completadas', () => {
    render(<Progreso estado="confirmado" />)
    expect(screen.getByText('confirmado').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('borrador').closest('li')).not.toHaveAttribute('aria-current')
  })
  it('un pedido cancelado no muestra etapas', () => {
    render(<Progreso estado="cancelado" />)
    expect(screen.getByText('Cancelado')).toBeInTheDocument()
    expect(screen.queryByText('enviado')).toBeNull()
  })
})

describe('alertasStockBajo', () => {
  const item = (sku: string, disp: string, min: string, bajo: boolean) => ({
    producto_id: sku,
    sku,
    nombre: sku,
    stock_actual: disp,
    stock_reservado: '0',
    stock_disponible: disp,
    stock_minimo: min,
    bajo_minimo: bajo,
  })
  it('solo los bajo mínimo, el mayor déficit primero', () => {
    const r = alertasStockBajo([item('ok', '50', '10', false), item('leve', '8', '10', true), item('grave', '0', '40', true)])
    expect(r.map((i) => i.sku)).toEqual(['grave', 'leve'])
  })
})
