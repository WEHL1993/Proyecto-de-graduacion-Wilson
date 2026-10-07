import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProductoOut } from '../types'
import {
  FORM_AJUSTE_VACIO,
  FORM_PRODUCTO_VACIO,
  presentacion,
  ProductsView,
  stockResultante,
  textoError,
  validarAjuste,
  validarProducto,
} from './ProductsView'

const sesion = vi.hoisted(() => ({ permisos: [] as string[] }))
vi.mock('../app/providers/AuthProvider', () => ({
  useAuth: () => ({
    usuario: { id: 'yo', nombre_completo: 'Admin', roles: [], permisos: sesion.permisos },
    can: (p: string) => sesion.permisos.includes(p),
    canAny: (ps: readonly string[]) => ps.some((p) => sesion.permisos.includes(p)),
  }),
}))

const api = vi.hoisted(() => ({
  listarProductos: vi.fn(),
  crearProducto: vi.fn(),
  actualizarProducto: vi.fn(),
  darDeBajaProducto: vi.fn(),
  reactivarProducto: vi.fn(),
  listarCategorias: vi.fn(),
  listarProveedores: vi.fn(),
  ajustarStock: vi.fn(),
}))
vi.mock('../services/productsApi', () => ({
  listarProductos: api.listarProductos,
  crearProducto: api.crearProducto,
  actualizarProducto: api.actualizarProducto,
  darDeBajaProducto: api.darDeBajaProducto,
  reactivarProducto: api.reactivarProducto,
}))
vi.mock('../services/catalogApi', () => ({
  listarCategorias: api.listarCategorias,
  listarProveedores: api.listarProveedores,
}))
vi.mock('../services/inventoryApi', () => ({ ajustarStock: api.ajustarStock }))

const TODOS = ['inventario:leer', 'inventario:ajustar', 'productos:crear', 'productos:editar', 'productos:eliminar']

const producto = (o: Partial<ProductoOut> = {}): ProductoOut => ({
  id: 'p1',
  sku: 'COLA-3030',
  nombre: 'Gaseosa Cola 3030',
  categoria_id: 'c1',
  categoria: 'Gaseosas',
  proveedor_id: null,
  unidad_medida: 'unidad',
  precio_venta: '12.50',
  costo_unitario: '8.00',
  stock_minimo: '10.00',
  unidades_por_paquete: 6,
  medida_ml: 3030,
  sabor: 'COLA',
  activo: true,
  stock_actual: '40.00',
  stock_reservado: '10.00',
  stock_disponible: '30.00',
  creado_en: '2026-01-01T00:00:00Z',
  ...o,
})

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <ProductsView />
    </QueryClientProvider>,
  )
}

const pagina = (items: ProductoOut[]) => ({ items, total: items.length, limit: 25, offset: 0 })

beforeEach(() => {
  vi.clearAllMocks()
  sesion.permisos = TODOS
  api.listarProductos.mockResolvedValue(pagina([producto()]))
  api.listarCategorias.mockResolvedValue([{ id: 'c1', nombre: 'Gaseosas' }])
  api.listarProveedores.mockResolvedValue([{ id: 's1', nombre: 'Proveedor Uno' }])
})

describe('validarProducto', () => {
  const valido = { ...FORM_PRODUCTO_VACIO, sku: 'A-1', nombre: 'Agua', categoria_id: 'c1' }
  it('acepta un alta completa', () => expect(validarProducto(valido)).toEqual({}))
  it('exige SKU, nombre y categoría', () => {
    expect(Object.keys(validarProducto(FORM_PRODUCTO_VACIO)).sort()).toEqual(['categoria_id', 'nombre', 'sku'])
  })
  it('rechaza precios, costos y mínimos negativos o no numéricos', () => {
    const e = validarProducto({ ...valido, precio_venta: '-1', costo_unitario: 'abc', stock_minimo: '' })
    expect(Object.keys(e).sort()).toEqual(['costo_unitario', 'precio_venta', 'stock_minimo'])
  })
  it('limita el SKU a 30 caracteres', () => {
    expect(validarProducto({ ...valido, sku: 'x'.repeat(31) }).sku).toBeDefined()
  })
})

describe('presentación en paquete (M02)', () => {
  const valido = { ...FORM_PRODUCTO_VACIO, sku: 'A-1', nombre: 'Agua', categoria_id: 'c1' }
  it('los valores por defecto del formulario siguen siendo válidos (compatibilidad)', () => {
    expect(FORM_PRODUCTO_VACIO.unidades_por_paquete).toBe('1')
    expect(validarProducto(valido)).toEqual({})
  })
  it('exige unidades por paquete entero >= 1', () => {
    for (const malo of ['0', '', '1.5', '-2', 'x'])
      expect(validarProducto({ ...valido, unidades_por_paquete: malo }).unidades_por_paquete).toBeDefined()
    expect(validarProducto({ ...valido, unidades_por_paquete: '24' })).toEqual({})
  })
  it('la medida es opcional pero, si se indica, entera >= 1', () => {
    expect(validarProducto({ ...valido, medida_ml: '' })).toEqual({})
    expect(validarProducto({ ...valido, medida_ml: '3030' })).toEqual({})
    expect(validarProducto({ ...valido, medida_ml: '0' }).medida_ml).toBeDefined()
    expect(validarProducto({ ...valido, medida_ml: '1.5' }).medida_ml).toBeDefined()
  })
  it('limita el sabor a 60 caracteres', () => {
    expect(validarProducto({ ...valido, sabor: 'x'.repeat(61) }).sabor).toBeDefined()
  })
  it('formatea la presentación', () => {
    expect(presentacion({ unidades_por_paquete: 6, medida_ml: 3030, sabor: 'COLA' })).toBe('6 × 3030 ml · COLA')
    expect(presentacion({ unidades_por_paquete: 12, medida_ml: null, sabor: null })).toBe('12')
  })
  it('la tabla muestra la presentación del producto', async () => {
    montar()
    const fila = (await screen.findByText('Gaseosa Cola 3030')).closest('tr')!
    expect(within(fila).getByText('6 × 3030 ml · COLA')).toBeInTheDocument()
  })
})

describe('validarAjuste / stockResultante', () => {
  const p = { stock_actual: '40.00', stock_reservado: '10.00' }
  const ok = { tipo: 'incremento' as const, cantidad: '5', motivo: 'Conteo físico' }

  it('calcula el stock resultante por tipo', () => {
    expect(stockResultante('incremento', '5', 40)).toBe(45)
    expect(stockResultante('decremento', '5', 40)).toBe(35)
    expect(stockResultante('fijar', '12', 40)).toBe(12)
    expect(stockResultante('fijar', '', 40)).toBeNull()
  })
  it('acepta ajustes válidos', () => {
    expect(validarAjuste(ok, p)).toEqual({})
    expect(validarAjuste({ ...ok, tipo: 'fijar', cantidad: '10' }, p)).toEqual({}) // = reservado
  })
  it('no deja el stock por debajo de lo reservado', () => {
    expect(validarAjuste({ ...ok, tipo: 'decremento', cantidad: '31' }, p).cantidad).toMatch(/reservado/)
    expect(validarAjuste({ ...ok, tipo: 'fijar', cantidad: '9' }, p).cantidad).toMatch(/reservado/)
  })
  it('exige cantidad > 0 en incremento/decremento y un cambio real en fijar', () => {
    expect(validarAjuste({ ...ok, cantidad: '0' }, p).cantidad).toBeDefined()
    expect(validarAjuste({ ...ok, cantidad: '-2' }, p).cantidad).toBeDefined()
    expect(validarAjuste({ ...ok, tipo: 'fijar', cantidad: '40' }, p).cantidad).toMatch(/no modifica/)
    expect(validarAjuste(FORM_AJUSTE_VACIO, p).cantidad).toBeDefined()
  })
  it('exige un motivo de al menos 5 caracteres', () => {
    expect(validarAjuste({ ...ok, motivo: 'abc' }, p).motivo).toBeDefined()
    expect(validarAjuste({ ...ok, motivo: '   ' }, p).motivo).toBeDefined()
  })
})

describe('textoError', () => {
  const conCodigo = (codigo: string, detalle: Record<string, unknown>) =>
    new AxiosError('x', '409', undefined, undefined, {
      status: 409,
      data: { codigo, mensaje: 'Mensaje base', detalle },
    } as never)

  it('agrega el detalle de PRODUCTO_EN_USO', () => {
    const t = textoError(conCodigo('PRODUCTO_EN_USO', { stock_reservado: '5', cargas_vigentes: ['a', 'b'] }))
    expect(t).toContain('Mensaje base')
    expect(t).toContain('cargas vigentes: 2')
  })
  it('agrega el detalle de STOCK_INSUFICIENTE', () => {
    expect(textoError(conCodigo('STOCK_INSUFICIENTE', { stock_actual: '20', stock_reservado: '8' }))).toContain('reservado: 8')
  })
})

describe('<ProductsView />', () => {
  it('lista productos con categoría, stock y disponible', async () => {
    montar()
    const fila = (await screen.findByText('Gaseosa Cola 3030')).closest('tr')!
    expect(within(fila).getByText('Gaseosas')).toBeInTheDocument()
    expect(within(fila).getByText('COLA-3030')).toBeInTheDocument()
    expect(api.listarProductos).toHaveBeenCalledWith(expect.objectContaining({ activo: true, offset: 0 }))
  })

  it('con todos los permisos muestra todas las acciones', async () => {
    montar()
    await screen.findByText('Gaseosa Cola 3030')
    expect(screen.getByRole('button', { name: '+ Nuevo producto' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar COLA-3030' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ajustar stock de COLA-3030' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dar de baja COLA-3030' })).toBeInTheDocument()
  })

  it('un rol solo de lectura no ve ninguna acción de escritura', async () => {
    sesion.permisos = ['inventario:leer']
    montar()
    await screen.findByText('Gaseosa Cola 3030')
    expect(screen.queryByRole('button', { name: '+ Nuevo producto' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ajustar stock/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dar de baja/ })).not.toBeInTheDocument()
  })

  it('Bodega ajusta stock pero no gestiona productos', async () => {
    sesion.permisos = ['inventario:leer', 'inventario:ajustar']
    montar()
    await screen.findByText('Gaseosa Cola 3030')
    expect(screen.getByRole('button', { name: 'Ajustar stock de COLA-3030' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Nuevo producto' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dar de baja/ })).not.toBeInTheDocument()
  })

  it('crea un producto: valida, envía los datos y refresca', async () => {
    api.crearProducto.mockResolvedValue(producto({ id: 'p2', sku: 'AGUA-1' }))
    montar()
    await screen.findByText('Gaseosa Cola 3030')
    fireEvent.click(screen.getByRole('button', { name: '+ Nuevo producto' }))

    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear producto' }))
    expect((await within(dialogo).findAllByRole('alert')).length).toBeGreaterThanOrEqual(3)
    expect(api.crearProducto).not.toHaveBeenCalled()

    const [sku, , nombre] = within(dialogo).getAllByRole('textbox')
    fireEvent.change(sku, { target: { value: 'AGUA-1' } })
    fireEvent.change(nombre, { target: { value: 'Agua pura' } })
    await waitFor(() => expect(within(dialogo).getByRole('option', { name: 'Gaseosas' })).toBeInTheDocument())
    fireEvent.change(within(dialogo).getAllByRole('combobox')[0], { target: { value: 'c1' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear producto' }))

    await waitFor(() => expect(api.crearProducto).toHaveBeenCalledTimes(1))
    expect(api.crearProducto.mock.calls[0][0]).toMatchObject({
      sku: 'AGUA-1',
      nombre: 'Agua pura',
      categoria_id: 'c1',
      proveedor_id: null,
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('muestra el error del servidor (SKU duplicado) sin cerrar el formulario', async () => {
    api.crearProducto.mockRejectedValue(
      new AxiosError('x', '409', undefined, undefined, {
        status: 409,
        data: { codigo: 'SKU_DUPLICADO', mensaje: 'Ya existe un producto con ese SKU.' },
      } as never),
    )
    montar()
    await screen.findByText('Gaseosa Cola 3030')
    fireEvent.click(screen.getByRole('button', { name: '+ Nuevo producto' }))
    const dialogo = await screen.findByRole('dialog')
    const [sku, , nombre] = within(dialogo).getAllByRole('textbox')
    fireEvent.change(sku, { target: { value: 'COLA-3030' } })
    fireEvent.change(nombre, { target: { value: 'Otra cola' } })
    await waitFor(() => expect(within(dialogo).getByRole('option', { name: 'Gaseosas' })).toBeInTheDocument())
    fireEvent.change(within(dialogo).getAllByRole('combobox')[0], { target: { value: 'c1' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear producto' }))

    expect(await within(dialogo).findByText('Ya existe un producto con ese SKU.')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('edita un producto enviando el proveedor como null cuando se quita', async () => {
    api.actualizarProducto.mockResolvedValue(producto())
    montar()
    fireEvent.click(await screen.findByRole('button', { name: 'Editar COLA-3030' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByDisplayValue('Gaseosa Cola 3030')).toBeInTheDocument()
    fireEvent.change(within(dialogo).getByDisplayValue('12.50'), { target: { value: '15' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(api.actualizarProducto).toHaveBeenCalledTimes(1))
    const [id, datos] = api.actualizarProducto.mock.calls[0]
    expect(id).toBe('p1')
    expect(datos).toMatchObject({ precio_venta: '15', proveedor_id: null })
  })

  it('da de baja tras confirmar y muestra PRODUCTO_EN_USO si el servidor lo bloquea', async () => {
    api.darDeBajaProducto.mockRejectedValue(
      new AxiosError('x', '409', undefined, undefined, {
        status: 409,
        data: {
          codigo: 'PRODUCTO_EN_USO',
          mensaje: 'No se puede dar de baja.',
          detalle: { stock_reservado: '10', cargas_vigentes: ['c1'] },
        },
      } as never),
    )
    montar()
    fireEvent.click(await screen.findByRole('button', { name: 'Dar de baja COLA-3030' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Dar de baja' }))

    await waitFor(() => expect(api.darDeBajaProducto).toHaveBeenCalledWith('p1'))
    expect(await within(dialogo).findByText(/cargas vigentes: 1/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('en «Dados de baja» ofrece reactivar y oculta ajustar/dar de baja', async () => {
    api.listarProductos.mockImplementation(async (f: { activo: boolean }) =>
      pagina([producto({ activo: f.activo })]),
    )
    api.reactivarProducto.mockResolvedValue(producto())
    montar()
    await screen.findByText('Gaseosa Cola 3030')
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'bajas' } })

    const reactivar = await screen.findByRole('button', { name: 'Reactivar COLA-3030' })
    expect(api.listarProductos).toHaveBeenLastCalledWith(expect.objectContaining({ activo: false }))
    expect(screen.queryByRole('button', { name: /Ajustar stock/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dar de baja COLA/ })).not.toBeInTheDocument()
    fireEvent.click(reactivar)
    await waitFor(() => expect(api.reactivarProducto).toHaveBeenCalledWith('p1'))
  })

  it('ajusta stock mostrando el resultante y enviando el cuerpo esperado', async () => {
    api.ajustarStock.mockResolvedValue({})
    montar()
    fireEvent.click(await screen.findByRole('button', { name: 'Ajustar stock de COLA-3030' }))
    const dialogo = await screen.findByRole('dialog')

    fireEvent.change(within(dialogo).getByLabelText('Tipo de ajuste'), { target: { value: 'decremento' } })
    fireEvent.change(within(dialogo).getByLabelText(/^Cantidad/), { target: { value: '35' } })
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Merma por rotura' } })
    // 40 - 35 = 5 < 10 reservado: se bloquea en el cliente.
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar ajuste' }))
    expect(await within(dialogo).findByText(/por debajo de lo reservado/)).toBeInTheDocument()
    expect(api.ajustarStock).not.toHaveBeenCalled()

    fireEvent.change(within(dialogo).getByLabelText(/^Cantidad/), { target: { value: '12' } })
    expect(within(dialogo).getByText('28')).toBeInTheDocument() // stock resultante
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aplicar ajuste' }))

    await waitFor(() => expect(api.ajustarStock).toHaveBeenCalledTimes(1))
    expect(api.ajustarStock.mock.calls[0][0]).toEqual({
      producto_id: 'p1',
      tipo: 'decremento',
      cantidad: '12',
      motivo: 'Merma por rotura',
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
