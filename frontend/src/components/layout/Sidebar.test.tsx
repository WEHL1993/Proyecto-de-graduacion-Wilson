import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PackageCheck } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { iconoDePantalla } from './iconos'

const recepcion = {
  clave: 'recepcion', etiqueta: 'Recepción de mercadería', ruta: '/recepcion',
  ruta_prefijo: null, grupo: 'Inventario', orden: 50,
}

function montar(menu: typeof recepcion[]) {
  return render(<MemoryRouter initialEntries={['/recepcion']}>
    <Sidebar menu={menu} colapsado={false} abierto={false}
      alExpandir={() => {}} alCerrar={() => {}} />
  </MemoryRouter>)
}

describe('Recepción en el menú del servidor', () => {
  it('aparece una vez dentro de Inventario y usa PackageCheck', () => {
    montar([recepcion])
    const grupo = screen.getByText('Inventario').parentElement!
    const enlaces = within(grupo).getAllByRole('link', { name: recepcion.etiqueta })
    expect(enlaces).toHaveLength(1)
    expect(enlaces[0]).toHaveAttribute('href', '/recepcion')
    expect(enlaces[0]).toHaveAttribute('aria-current', 'page')
    expect(iconoDePantalla('recepcion')).toBe(PackageCheck)
  })

  it('no agrega recepción cuando el servidor no la autoriza', () => {
    montar([])
    expect(screen.queryByRole('link', { name: recepcion.etiqueta })).not.toBeInTheDocument()
  })
})
