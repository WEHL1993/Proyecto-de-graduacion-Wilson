import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { LoadPlanItem } from '../../types'
import { LoadPlanTable, errorCantidad, estadoStock } from './LoadPlanTable'

const item = (o: Partial<LoadPlanItem>): LoadPlanItem => ({
  producto_id: 'p1',
  sku: 'BEB-0034',
  producto_nombre: 'Gaseosa 2L',
  cantidad_predicha: '210',
  stock_disponible: '150',
  cantidad_sugerida: '150',
  cantidad_aprobada: null,
  ajustado_por_stock: true,
  ...o,
})

describe('estadoStock', () => {
  it('sin existencia, limitado, o sin marca en otro caso', () => {
    expect(estadoStock(item({ stock_disponible: '0', cantidad_sugerida: '0' }))).toBe('sin_existencia')
    expect(estadoStock(item({}))).toBe('limitado')
    expect(estadoStock(item({ ajustado_por_stock: false, stock_disponible: '500' }))).toBe('ok')
  })
})

describe('errorCantidad (nunca mayor al stock disponible)', () => {
  it('acepta 0 y el tope exacto', () => {
    expect(errorCantidad('0', 150)).toBeNull()
    expect(errorCantidad('150', '150')).toBeNull()
  })
  it('rechaza vacío, negativos, texto y excedentes', () => {
    expect(errorCantidad('', 150)).toMatch(/cantidad/i)
    expect(errorCantidad('-1', 150)).toMatch(/mayor o igual/)
    expect(errorCantidad('abc', 150)).toMatch(/mayor o igual/)
    expect(errorCantidad('151', 150)).toMatch(/exceder/)
  })
})

describe('<LoadPlanTable />', () => {
  const props = {
    items: [
      item({}),
      item({ producto_id: 'p2', sku: 'LIM-0003', stock_disponible: '0', cantidad_sugerida: '0' }),
    ],
    seleccion: new Set(['p1']),
    cantidades: { p1: '200', p2: '0' },
    onSeleccion: vi.fn(),
    onSeleccionTodos: vi.fn(),
    onCantidad: vi.fn(),
  }

  it('muestra badges de alerta con tooltip de demanda original vs. ajustada', () => {
    render(<LoadPlanTable {...props} editable />)
    expect(screen.getByLabelText(/Limitado por stock/)).toHaveAttribute(
      'title',
      'Demanda original: 210 · Cantidad ajustada: 150',
    )
    expect(screen.getByLabelText('Sin existencia')).toBeInTheDocument()
  })

  it('marca inválida una cantidad aprobada que excede el stock y propaga los cambios', () => {
    render(<LoadPlanTable {...props} editable />)
    const entrada = screen.getByLabelText('Cantidad aprobada de BEB-0034')
    expect(entrada).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(/No puede exceder el stock disponible/)).toBeInTheDocument()
    fireEvent.change(entrada, { target: { value: '120' } })
    expect(props.onCantidad).toHaveBeenCalledWith('p1', '120')
  })

  it('en solo lectura no hay campos editables', () => {
    render(<LoadPlanTable {...props} editable={false} />)
    expect(screen.queryByLabelText('Cantidad aprobada de BEB-0034')).not.toBeInTheDocument()
  })
})
