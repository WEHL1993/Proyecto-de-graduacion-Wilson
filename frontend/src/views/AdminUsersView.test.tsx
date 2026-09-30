import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UsuarioOut } from '../types'
import { AdminUsersView, FORM_VACIO, validarFormulario } from './AdminUsersView'

vi.mock('../app/providers/AuthProvider', () => ({
  useAuth: () => ({ usuario: { id: 'yo', nombre_completo: 'Admin', roles: ['Admin'], permisos: [] }, can: () => true, canAny: () => true }),
}))

const api = vi.hoisted(() => ({
  listarUsuarios: vi.fn(),
  listarRoles: vi.fn(),
  crearUsuario: vi.fn(),
  actualizarUsuario: vi.fn(),
  cambiarEstadoUsuario: vi.fn(),
  listarRutas: vi.fn(),
}))
vi.mock('../services/usersApi', () => api)
vi.mock('../services/catalogApi', () => ({ listarRutas: api.listarRutas }))

const usuario = (o: Partial<UsuarioOut>): UsuarioOut => ({
  id: 'u1',
  email: 'ana@ds.gt',
  nombre_completo: 'Ana Ventas',
  activo: true,
  roles: ['Ventas'],
  rutas: [{ id: 'r1', codigo: 'R-01', nombre: 'Ruta 1' }],
  creado_en: '2026-01-01T00:00:00Z',
  ...o,
})

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <AdminUsersView />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listarRoles.mockResolvedValue([
    { id: 1, nombre: 'Admin' },
    { id: 2, nombre: 'Ventas' },
    { id: 3, nombre: 'Proveedor' },
  ])
  api.listarRutas.mockResolvedValue([{ id: 'r1', codigo: 'R-01', nombre: 'Ruta 1' }, { id: 'r2', codigo: 'R-02', nombre: 'Ruta 2' }])
  api.listarUsuarios.mockResolvedValue({
    total: 2,
    usuarios: [usuario({}), usuario({ id: 'yo', email: 'admin@ds.gt', nombre_completo: 'Admin', roles: ['Admin'], rutas: [] })],
  })
})

describe('validarFormulario', () => {
  const valido = { ...FORM_VACIO, email: 'a@b.co', nombre_completo: 'Ana Ruiz', password: 'ClaveSegura1', roles: ['Ventas'] }
  it('acepta un alta completa', () => expect(validarFormulario(valido, false)).toEqual({}))
  it('exige correo, nombre, contraseña y rol en el alta', () => {
    expect(Object.keys(validarFormulario(FORM_VACIO, false)).sort()).toEqual(['email', 'nombre_completo', 'password', 'roles'])
  })
  it('en edición la contraseña es opcional pero, si se escribe, mínimo 8', () => {
    expect(validarFormulario({ ...valido, password: '' }, true)).toEqual({})
    expect(validarFormulario({ ...valido, password: 'corta' }, true).password).toBeDefined()
  })
  it('el rol Proveedor exige un UUID de proveedor', () => {
    const f = { ...valido, roles: ['Proveedor'] }
    expect(validarFormulario(f, false).proveedor_id).toBeDefined()
    expect(validarFormulario({ ...f, proveedor_id: '6f1c2b1e-7f4c-4a55-9a53-0d5b6f2f7a11' }, false)).toEqual({})
  })
})

describe('<AdminUsersView />', () => {
  it('lista usuarios con badges de rol, rutas y estado', async () => {
    montar()
    const fila = (await screen.findByText('Ana Ventas')).closest('tr')!
    expect(within(fila).getByText('Ventas')).toBeInTheDocument()
    expect(within(fila).getByText('R-01')).toBeInTheDocument()
    expect(within(fila).getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('el toggle desactiva al usuario; la propia cuenta no se puede desactivar', async () => {
    api.cambiarEstadoUsuario.mockResolvedValue(usuario({ activo: false }))
    montar()
    const toggle = await screen.findByRole('switch', { name: /desactivar a ana ventas/i })
    fireEvent.click(toggle)
    await waitFor(() => expect(api.cambiarEstadoUsuario).toHaveBeenCalledWith('u1', false))
    expect(screen.getByRole('switch', { name: /a admin$/i })).toBeDisabled()
  })

  it('crear: valida en cliente y luego envía el alta con roles y rutas', async () => {
    api.crearUsuario.mockResolvedValue(usuario({}))
    montar()
    fireEvent.click(await screen.findByRole('button', { name: '+ Nuevo usuario' }))
    const dialogo = await screen.findByRole('dialog')

    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear usuario' }))
    expect(await within(dialogo).findByText('Ingrese un correo válido.')).toBeInTheDocument()
    expect(api.crearUsuario).not.toHaveBeenCalled()

    fireEvent.change(within(dialogo).getByLabelText(/^Correo electrónico/), { target: { value: 'nuevo@ds.gt' } })
    fireEvent.change(within(dialogo).getByLabelText(/^Nombre completo/), { target: { value: 'Nuevo Vendedor' } })
    fireEvent.change(within(dialogo).getByLabelText(/^Contraseña/), { target: { value: 'ClaveSegura1' } })
    fireEvent.click(await within(dialogo).findByLabelText('Ventas'))
    fireEvent.click(await within(dialogo).findByLabelText('R-02 · Ruta 2'))
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear usuario' }))

    await waitFor(() => expect(api.crearUsuario).toHaveBeenCalled())
    expect(api.crearUsuario.mock.calls[0][0]).toMatchObject({
      email: 'nuevo@ds.gt',
      roles: ['Ventas'],
      ruta_ids: ['r2'],
      proveedor_id: null,
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('editar precarga los datos y no permite cambiar el correo', async () => {
    api.actualizarUsuario.mockResolvedValue(usuario({}))
    montar()
    fireEvent.click(await screen.findByRole('button', { name: 'Editar a Ana Ventas' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByLabelText(/^Correo electrónico/)).toBeDisabled()
    expect(within(dialogo).getByLabelText(/^Nombre completo/)).toHaveValue('Ana Ventas')
    await waitFor(() => expect(within(dialogo).getByLabelText('R-01 · Ruta 1')).toBeChecked())

    fireEvent.change(within(dialogo).getByLabelText(/^Nombre completo/), { target: { value: 'Ana M. Ventas' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(api.actualizarUsuario).toHaveBeenCalled())
    const [id, datos] = api.actualizarUsuario.mock.calls[0]
    expect(id).toBe('u1')
    expect(datos).toMatchObject({ nombre_completo: 'Ana M. Ventas', roles: ['Ventas'], ruta_ids: ['r1'] })
    expect(datos).not.toHaveProperty('password')
  })

  it('muestra el error del servidor dentro del modal (correo duplicado)', async () => {
    const { AxiosError } = await import('axios')
    api.crearUsuario.mockRejectedValue(
      new AxiosError('x', '409', undefined, undefined, {
        status: 409,
        data: { codigo: 'EMAIL_DUPLICADO', mensaje: 'Ya existe un usuario con ese correo.' },
      } as never),
    )
    montar()
    fireEvent.click(await screen.findByRole('button', { name: '+ Nuevo usuario' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText(/^Correo electrónico/), { target: { value: 'dup@ds.gt' } })
    fireEvent.change(within(dialogo).getByLabelText(/^Nombre completo/), { target: { value: 'Nombre Dup' } })
    fireEvent.change(within(dialogo).getByLabelText(/^Contraseña/), { target: { value: 'ClaveSegura1' } })
    fireEvent.click(await within(dialogo).findByLabelText('Ventas'))
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear usuario' }))
    expect(await within(dialogo).findByText('Ya existe un usuario con ese correo.')).toBeInTheDocument()
  })
})
