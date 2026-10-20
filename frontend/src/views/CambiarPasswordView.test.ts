import { describe, expect, it } from 'vitest'
import { validarPassword } from './CambiarPasswordView'

describe('validarPassword', () => {
  it('acepta un cambio válido', () => {
    expect(validarPassword({ actual: 'Temporal123', nueva: 'NuevaClave456', confirmacion: 'NuevaClave456' })).toEqual({})
  })

  it('exige la actual, mínimo 8 caracteres y confirmación idéntica', () => {
    const e = validarPassword({ actual: '', nueva: 'corta', confirmacion: 'otra' })
    expect(e.actual).toBeDefined()
    expect(e.nueva).toBeDefined()
    expect(e.confirmacion).toBeDefined()
  })

  it('rechaza una nueva igual a la actual', () => {
    const e = validarPassword({ actual: 'Temporal123', nueva: 'Temporal123', confirmacion: 'Temporal123' })
    expect(e.nueva).toMatch(/distinta/)
  })
})
