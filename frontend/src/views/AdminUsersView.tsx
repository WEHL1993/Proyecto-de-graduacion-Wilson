import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../app/providers/AuthProvider'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { useRoles, useUsuarioActions, useUsuarios } from '../hooks/useUsers'
import { listarRutas } from '../services/catalogApi'
import type { UsuarioCreate, UsuarioOut, UsuarioUpdate } from '../types'
import { mensajeError } from '../utils/errors'
import { fmtFecha } from '../utils/format'

const ROL_PROVEEDOR = 'Proveedor'
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const COLOR_ROL: Record<string, string> = {
  Administrador: 'bg-bad/10 text-bad',
  Gerente: 'bg-brand/10 text-brand',
  EncargadoVentas: 'bg-good/10 text-good',
  EncargadoInventario: 'bg-warn/10 text-warn',
  EncargadoBodega: 'bg-warn/10 text-warn',
  EncargadoCompras: 'bg-brand/10 text-brand',
  Liquidador: 'bg-good/10 text-good',
}

export function RolBadge({ rol }: { rol: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${COLOR_ROL[rol] ?? 'bg-surface text-muted'}`}>
      {rol}
    </span>
  )
}

// ---------------------------------------------------------------- formulario
export interface FormUsuario {
  email: string
  nombre_completo: string
  password: string
  roles: string[]
  ruta_ids: string[]
  proveedor_id: string
}

export const FORM_VACIO: FormUsuario = {
  email: '',
  nombre_completo: '',
  password: '',
  roles: [],
  ruta_ids: [],
  proveedor_id: '',
}

export const formDesdeUsuario = (u: UsuarioOut): FormUsuario => ({
  email: u.email,
  nombre_completo: u.nombre_completo,
  password: '',
  roles: [...u.roles],
  ruta_ids: u.rutas.map((r) => r.id),
  proveedor_id: u.proveedor_id ?? '',
})

/** Errores por campo; vacío = válido. En edición la contraseña es opcional. */
export function validarFormulario(f: FormUsuario, edicion: boolean): Partial<Record<keyof FormUsuario, string>> {
  const e: Partial<Record<keyof FormUsuario, string>> = {}
  if (!edicion && !EMAIL.test(f.email.trim())) e.email = 'Ingrese un correo válido.'
  if (f.nombre_completo.trim().length < 3) e.nombre_completo = 'Mínimo 3 caracteres.'
  if (f.password ? f.password.length < 8 : !edicion) e.password = 'Mínimo 8 caracteres.'
  if (!f.roles.length) e.roles = 'Seleccione al menos un rol.'
  if (f.roles.includes(ROL_PROVEEDOR) && !UUID.test(f.proveedor_id.trim()))
    e.proveedor_id = 'El rol Proveedor requiere el identificador (UUID) del proveedor.'
  return e
}

const aCreate = (f: FormUsuario): UsuarioCreate => ({
  email: f.email.trim(),
  nombre_completo: f.nombre_completo.trim(),
  password: f.password,
  roles: f.roles,
  ruta_ids: f.ruta_ids,
  proveedor_id: f.roles.includes(ROL_PROVEEDOR) ? f.proveedor_id.trim() : null,
  activo: true,
})

const aUpdate = (f: FormUsuario): UsuarioUpdate => ({
  nombre_completo: f.nombre_completo.trim(),
  roles: f.roles,
  ruta_ids: f.ruta_ids,
  proveedor_id: f.roles.includes(ROL_PROVEEDOR) ? f.proveedor_id.trim() : null,
  ...(f.password ? { password: f.password } : {}),
})

const alternar = (lista: string[], valor: string) =>
  lista.includes(valor) ? lista.filter((v) => v !== valor) : [...lista, valor]

function ModalUsuario({ usuario, onCerrar }: { usuario: UsuarioOut | null; onCerrar: () => void }) {
  const edicion = usuario !== null
  const [form, setForm] = useState<FormUsuario>(usuario ? formDesdeUsuario(usuario) : FORM_VACIO)
  const [intento, setIntento] = useState(false)
  const roles = useRoles()
  const rutas = useQuery({ queryKey: ['rutas'], queryFn: listarRutas })
  const { crear, actualizar } = useUsuarioActions()
  const mutacion = edicion ? actualizar : crear
  const errores = validarFormulario(form, edicion)
  const set = <K extends keyof FormUsuario>(k: K, v: FormUsuario[K]) => setForm((f) => ({ ...f, [k]: v }))

  const enviar = (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    if (Object.keys(errores).length) return
    const alTerminar = { onSuccess: onCerrar }
    if (usuario) actualizar.mutate({ id: usuario.id, datos: aUpdate(form) }, alTerminar)
    else crear.mutate(aCreate(form), alTerminar)
  }
  const mostrar = (k: keyof FormUsuario) =>
    intento && errores[k] ? (
      <span role="alert" className="text-xs font-normal text-bad">
        {errores[k]}
      </span>
    ) : null

  return (
    <Modal
      titulo={edicion ? `Editar usuario` : 'Nuevo usuario'}
      onCerrar={onCerrar}
      acciones={
        <>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button variant="primary" type="submit" form="form-usuario" disabled={mutacion.isPending}>
            {mutacion.isPending ? 'Guardando…' : edicion ? 'Guardar cambios' : 'Crear usuario'}
          </Button>
        </>
      }
    >
      <form id="form-usuario" onSubmit={enviar} noValidate className="flex flex-col gap-3">
        {mutacion.isError && <AlertBanner>{mensajeError(mutacion.error)}</AlertBanner>}
        <Campo etiqueta="Correo electrónico">
          <input
            type="email"
            value={form.email}
            disabled={edicion}
            onChange={(e) => set('email', e.target.value)}
            className={CLASE_INPUT}
            autoComplete="off"
          />
          {mostrar('email')}
        </Campo>
        <Campo etiqueta="Nombre completo">
          <input value={form.nombre_completo} onChange={(e) => set('nombre_completo', e.target.value)} className={CLASE_INPUT} />
          {mostrar('nombre_completo')}
        </Campo>
        <Campo etiqueta={edicion ? 'Nueva contraseña (opcional)' : 'Contraseña'}>
          <input
            type="password"
            value={form.password}
            onChange={(e) => set('password', e.target.value)}
            className={CLASE_INPUT}
            autoComplete="new-password"
            placeholder={edicion ? 'Dejar en blanco para conservarla' : 'Mínimo 8 caracteres'}
          />
          {mostrar('password')}
        </Campo>

        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-xs font-medium text-muted">Roles</legend>
          {roles.isLoading && <Cargando texto="Cargando roles…" />}
          <div className="grid grid-cols-2 gap-1">
            {roles.data?.map((r) => (
              <label key={r.id} className="flex items-center gap-2 text-sm" title={r.descripcion ?? undefined}>
                <input type="checkbox" checked={form.roles.includes(r.nombre)} onChange={() => set('roles', alternar(form.roles, r.nombre))} />
                {r.nombre}
              </label>
            ))}
          </div>
          {mostrar('roles')}
        </fieldset>

        {form.roles.includes(ROL_PROVEEDOR) && (
          <Campo etiqueta="Proveedor asociado (UUID)">
            <input value={form.proveedor_id} onChange={(e) => set('proveedor_id', e.target.value)} className={CLASE_INPUT} placeholder="00000000-0000-0000-0000-000000000000" />
            {mostrar('proveedor_id')}
          </Campo>
        )}

        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-xs font-medium text-muted">Rutas comerciales asignadas</legend>
          {rutas.isLoading && <Cargando texto="Cargando rutas…" />}
          <div className="grid max-h-36 grid-cols-2 gap-1 overflow-y-auto">
            {rutas.data?.map((r) => (
              <label key={r.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.ruta_ids.includes(r.id)} onChange={() => set('ruta_ids', alternar(form.ruta_ids, r.id))} />
                {r.codigo} · {r.nombre}
              </label>
            ))}
          </div>
          <p className="text-xs text-muted">Una ruta tiene un solo vendedor: asignarla aquí la quita de su titular actual.</p>
        </fieldset>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------- vista
export function AdminUsersView() {
  const { usuario: yo } = useAuth()
  const [q, setQ] = useState('')
  const [rol, setRol] = useState('')
  const [estado, setEstado] = useState<'' | 'activos' | 'inactivos'>('')
  const [modal, setModal] = useState<{ usuario: UsuarioOut | null } | null>(null)

  const usuarios = useUsuarios({ q: q.trim(), rol, activo: estado === '' ? undefined : estado === 'activos' })
  const roles = useRoles()
  const { cambiarEstado } = useUsuarioActions()

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Usuarios y roles</h1>
          <p className="text-sm text-muted">Alta, edición, asignación de roles y rutas, y activación de cuentas.</p>
        </div>
        <Button variant="primary" onClick={() => setModal({ usuario: null })}>
          + Nuevo usuario
        </Button>
      </header>

      <Card>
        <div className="mb-3 flex flex-wrap gap-3">
          <Campo etiqueta="Buscar">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre o correo" className={`${CLASE_INPUT} w-56`} />
          </Campo>
          <Campo etiqueta="Rol">
            <select value={rol} onChange={(e) => setRol(e.target.value)} className={CLASE_INPUT}>
              <option value="">Todos</option>
              {roles.data?.map((r) => (
                <option key={r.id}>{r.nombre}</option>
              ))}
            </select>
          </Campo>
          <Campo etiqueta="Estado">
            <select value={estado} onChange={(e) => setEstado(e.target.value as typeof estado)} className={CLASE_INPUT}>
              <option value="">Todos</option>
              <option value="activos">Activos</option>
              <option value="inactivos">Inactivos</option>
            </select>
          </Campo>
        </div>

        {cambiarEstado.isError && <AlertBanner>{mensajeError(cambiarEstado.error)}</AlertBanner>}
        {usuarios.isLoading && <Cargando texto="Cargando usuarios…" />}
        {usuarios.isError && <AlertBanner>{mensajeError(usuarios.error)}</AlertBanner>}
        {usuarios.data && !usuarios.data.usuarios.length && (
          <EmptyState titulo="Sin usuarios" detalle="Ningún usuario coincide con los filtros aplicados." />
        )}
        {!!usuarios.data?.usuarios.length && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Usuarios del sistema</caption>
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="py-2 pr-3">Usuario</th>
                  <th className="py-2 pr-3">Roles</th>
                  <th className="py-2 pr-3">Rutas</th>
                  <th className="py-2 pr-3">Último acceso</th>
                  <th className="py-2 pr-3">Activo</th>
                  <th className="py-2 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {usuarios.data.usuarios.map((u) => {
                  const propio = u.id === yo?.id
                  return (
                    <tr key={u.id} className="border-t border-line align-top">
                      <td className="py-2 pr-3">
                        <div className="font-medium">{u.nombre_completo}</div>
                        <div className="text-xs text-muted">{u.email}</div>
                      </td>
                      <td className="py-2 pr-3">
                        <div className="flex flex-wrap gap-1">
                          {u.roles.map((r) => (
                            <RolBadge key={r} rol={r} />
                          ))}
                        </div>
                      </td>
                      <td className="py-2 pr-3 text-xs">{u.rutas.length ? u.rutas.map((r) => r.codigo).join(', ') : <span className="text-muted">—</span>}</td>
                      <td className="num py-2 pr-3 text-xs">{fmtFecha(u.ultimo_login)}</td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={u.activo}
                          aria-label={`${u.activo ? 'Desactivar' : 'Activar'} a ${u.nombre_completo}`}
                          title={propio ? 'No puede desactivar su propia cuenta' : undefined}
                          disabled={propio || (cambiarEstado.isPending && cambiarEstado.variables?.id === u.id)}
                          onClick={() => cambiarEstado.mutate({ id: u.id, activo: !u.activo })}
                          className={`relative h-5 w-9 rounded-full transition disabled:opacity-50 ${u.activo ? 'bg-good' : 'bg-line'}`}
                        >
                          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${u.activo ? 'left-4' : 'left-0.5'}`} />
                        </button>
                        <span className="ml-2 text-xs text-muted">{u.activo ? 'Activo' : 'Inactivo'}</span>
                      </td>
                      <td className="py-2 text-right">
                        <Button onClick={() => setModal({ usuario: u })} aria-label={`Editar a ${u.nombre_completo}`}>
                          Editar
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">
              {usuarios.data.usuarios.length} de {usuarios.data.total} usuarios
            </p>
          </div>
        )}
      </Card>

      {modal && <ModalUsuario key={modal.usuario?.id ?? 'nuevo'} usuario={modal.usuario} onCerrar={() => setModal(null)} />}
    </div>
  )
}
