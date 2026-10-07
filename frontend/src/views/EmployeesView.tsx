import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { PestanasRutas } from '../components/common/PestanasRutas'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { usePermissions } from '../hooks/usePermissions'
import { useEmpleadoActions, useEmpleados } from '../hooks/useRoutesAdmin'
import type { EmpleadoOut } from '../types'
import { apiError, mensajeError } from '../utils/errors'

const POR_PAGINA = 25

/** Error por campo (`EmpleadoCreate`): nombre de 2 a 150 caracteres. */
export function validarEmpleado(nombre: string): string | null {
  const n = nombre.trim()
  if (n.length < 2) return 'Mínimo 2 caracteres.'
  if (n.length > 150) return 'Máximo 150 caracteres.'
  return null
}

/** Mensaje del servidor, con el detalle útil de `EMPLEADO_EN_USO`. */
export function textoErrorEmpleado(e: unknown): string {
  const api = apiError(e)
  const base = mensajeError(e)
  const d = api?.detalle as Record<string, unknown> | undefined
  if (api?.codigo === 'EMPLEADO_EN_USO' && Array.isArray(d?.rutas))
    return `${base} (rutas: ${d.rutas.length}).`
  return base
}

function ModalEmpleado({ empleado, onCerrar }: { empleado: EmpleadoOut | null; onCerrar: () => void }) {
  const edicion = empleado !== null
  const [nombre, setNombre] = useState(empleado?.nombre_completo ?? '')
  const [intento, setIntento] = useState(false)
  const { crear, actualizar } = useEmpleadoActions()
  const mutacion = edicion ? actualizar : crear
  const error = validarEmpleado(nombre)

  const enviar = (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    if (error) return
    const alTerminar = { onSuccess: onCerrar }
    if (empleado) actualizar.mutate({ id: empleado.id, datos: { nombre_completo: nombre.trim() } }, alTerminar)
    else crear.mutate({ nombre_completo: nombre.trim() }, alTerminar)
  }

  return (
    <Modal
      titulo={edicion ? 'Editar empleado' : 'Nuevo empleado'}
      onCerrar={onCerrar}
      acciones={
        <>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button variant="primary" type="submit" form="form-empleado" disabled={mutacion.isPending}>
            {mutacion.isPending ? 'Guardando…' : edicion ? 'Guardar cambios' : 'Crear empleado'}
          </Button>
        </>
      }
    >
      <form id="form-empleado" onSubmit={enviar} noValidate className="flex flex-col gap-3">
        {mutacion.isError && <AlertBanner>{textoErrorEmpleado(mutacion.error)}</AlertBanner>}
        <Campo etiqueta="Nombre completo">
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} className={CLASE_INPUT} maxLength={150} />
          {intento && error && (
            <span role="alert" className="text-xs font-normal text-bad">
              {error}
            </span>
          )}
        </Campo>
        <p className="text-xs text-muted">
          El personal de ruta no es un usuario del sistema: no inicia sesión. El vínculo con un usuario es opcional.
        </p>
      </form>
    </Modal>
  )
}

/** Personal de ruta (vendedor, chofer, auxiliar): alta, edición y baja lógica (M02). */
export function EmployeesView() {
  const { can } = usePermissions()
  const puedeGestionar = can('catalogos:gestionar')
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState<'activos' | 'bajas'>('activos')
  const [pagina, setPagina] = useState(0)
  const [modal, setModal] = useState<{ empleado: EmpleadoOut | null } | null>(null)
  const empleados = useEmpleados({ q: q.trim(), activo: estado === 'activos', limit: POR_PAGINA, offset: pagina * POR_PAGINA })
  const { darDeBaja, reactivar } = useEmpleadoActions()
  const total = empleados.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA))
  const error = darDeBaja.error ?? reactivar.error

  return (
    <div className="flex flex-col gap-4">
      <PestanasRutas />
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Personal de ruta</h1>
          <p className="text-sm text-muted">Empleados que integran los equipos de ruta.</p>
        </div>
        {puedeGestionar && (
          <Button variant="primary" onClick={() => setModal({ empleado: null })}>
            + Nuevo empleado
          </Button>
        )}
      </header>

      <Card>
        <div className="mb-3 flex flex-wrap gap-3">
          <Campo etiqueta="Buscar">
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setPagina(0)
              }}
              placeholder="Nombre"
              className={`${CLASE_INPUT} w-56`}
            />
          </Campo>
          <Campo etiqueta="Estado">
            <select
              value={estado}
              onChange={(e) => {
                setEstado(e.target.value as typeof estado)
                setPagina(0)
              }}
              className={CLASE_INPUT}
            >
              <option value="activos">Activos</option>
              <option value="bajas">Dados de baja</option>
            </select>
          </Campo>
        </div>

        {error && <AlertBanner>{textoErrorEmpleado(error)}</AlertBanner>}
        {empleados.isPending && <Cargando texto="Cargando empleados…" />}
        {empleados.isError && <AlertBanner>{mensajeError(empleados.error)}</AlertBanner>}
        {empleados.data && empleados.data.items.length === 0 && (
          <EmptyState titulo="Sin empleados" detalle="Ningún empleado coincide con los filtros aplicados." />
        )}
        {!!empleados.data?.items.length && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <caption className="sr-only">Personal de ruta</caption>
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-2 pr-3">Nombre</th>
                    <th className="py-2 pr-3">Usuario del sistema</th>
                    <th className="py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {empleados.data.items.map((e) => (
                    <tr key={e.id} className="border-b border-line last:border-0">
                      <td className="py-2 pr-3">
                        {e.nombre_completo}
                        {!e.activo && (
                          <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-muted">Baja</span>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-xs">{e.usuario_id ? 'Vinculado' : '—'}</td>
                      <td className="py-2 text-right">
                        {puedeGestionar && (
                          <div className="flex flex-wrap justify-end gap-1.5">
                            <Button onClick={() => setModal({ empleado: e })} aria-label={`Editar ${e.nombre_completo}`}>
                              Editar
                            </Button>
                            {e.activo ? (
                              <Button variant="danger" disabled={darDeBaja.isPending} onClick={() => darDeBaja.mutate(e.id)} aria-label={`Dar de baja a ${e.nombre_completo}`}>
                                Dar de baja
                              </Button>
                            ) : (
                              <Button disabled={reactivar.isPending} onClick={() => reactivar.mutate(e.id)} aria-label={`Reactivar a ${e.nombre_completo}`}>
                                Reactivar
                              </Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="num text-muted">
                {total} empleados · página {pagina + 1} de {paginas}
              </span>
              <div className="flex gap-2">
                <Button disabled={pagina === 0} onClick={() => setPagina((n) => n - 1)}>
                  Anterior
                </Button>
                <Button disabled={pagina + 1 >= paginas} onClick={() => setPagina((n) => n + 1)}>
                  Siguiente
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      {modal && <ModalEmpleado key={modal.empleado?.id ?? 'nuevo'} empleado={modal.empleado} onCerrar={() => setModal(null)} />}
    </div>
  )
}
