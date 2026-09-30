import { describe, expect, it } from 'vitest'
import { semaforoMape, sumarDias } from './format'

describe('semaforoMape (wireframe 2b)', () => {
  it('verde hasta 0.8·umbral, amarillo hasta el umbral, rojo por encima', () => {
    expect(semaforoMape(9.6, 12)).toBe('verde')
    expect(semaforoMape(9.7, 12)).toBe('amarillo')
    expect(semaforoMape(12, 12)).toBe('amarillo')
    expect(semaforoMape(13.2, 12)).toBe('rojo')
  })
  it('sin dato cuando el MAPE es nulo', () => {
    expect(semaforoMape(null, 12)).toBe('sin_dato')
  })
})

describe('sumarDias', () => {
  it('cruza fin de mes sin desfase de zona horaria', () => {
    expect(sumarDias('2026-01-31', 1)).toBe('2026-02-01')
    expect(sumarDias('2026-03-01', -1)).toBe('2026-02-28')
  })
})
