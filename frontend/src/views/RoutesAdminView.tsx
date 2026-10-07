import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { PestanasRutas } from '../components/common/PestanasRutas'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { usePermissions } from '../hooks/usePermissions'
import {
  useEquiposIncompletos,
  useRutaActions,
  useRutasAdmin,
  useRutasDesalineadas,
} from '../hooks/useRoutesAdmin'
import type { RutaAdminOut } from '../types'
import { apiError, mensajeError } from '../utils/errors'

export interface FormRuta {
  codigo: string
  nombre: string
  zona: string
}

export const FORM_RUTA_VACIO: FormRuta = { codigo: '', nombre: '', zona: '' }

/** Errores por campo; vacío = válido. Refleja `RutaCreate` (el código solo se fija al crear). */
export function validarRuta(f: FormRuta, edicion: boolean): Partial<Record<keyof FormRuta, string>> {
  const e: Partial<Record<keyof FormRuta, string>> = {}
  if (!edicion) {
    if (!f.codigo.trim()) e.codigo = 'El código es obligatorio.'
    else if (f.codigo.trim().length > 20) e.codigo = 'Máximo 20 caracteres.'
  }
  if (f.nombre.trim().length < 2) e.nombre = 'Mínimo 2 caracteres.'
  if (f.zona.length > 100) e.zona = 'Máximo 100 caracteres.'
  return e
}

const MOTIVO: Record<string, string> = {
  sin_equipo: 'sin equipo',
  sin_vendedor: 'sin vendedor',
  suma_distinta_de_100: 'reparto ≠ 100 %',
}

/** Mensaje del servidor con el detalle útil de las bajas bloqueadas. */
export function textoErrorRuta(e: unknown): string {
  const api = apiError(e)
  const base = mensajeError(e)
  const d = api?.detalle as Record<string, unknown> | undefined
  if (!api || !d) return base
  if (api.codigo === 'RUTA_CON_LIQUIDACIONES' && Array.isArray(d.liquidaciones))
    return `${base} (${d.liquidaciones.length} en borrador).`
  if (api.codigo === 'RUTA_CON_CARGAS_VIGENTES' && Array.isArray(d.cargas))
    return `${base} (${d.cargas.length} vigentes).`
  return base
}

function ModalRuta({ ruta, onCerrar }: { ruta: RutaAdminOut | null; onCerrar: () => void }) {
  const edicion = ruta !== null
  const [form, setForm] = useState<FormRuta>(
    ruta ? { codigo: ruta.codigo, nombre: ruta.nombre, zona: ruta.zona ?? '' } : FORM_RUTA_VACIO,
  )
  const [intento, setIntento] = useState(false)
  const { crear, actualizar } = useRutaActions()
  const mutacion = edicion ? actualizar : crear
  const errores = validarRuta(form, edicion)
  const set = <K extends keyof FormRuta>(k: K, v: FormRuta[K]) => setForm((f) => ({ ...f, [k]: v }))

  const enviar = (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    if (Object.keys(errores).length) return
    const alTerminar = { onSuccess: onCerrar }
    const zona = form.zona.trim() || null
    if (ruta) actualizar.mutate({ id: ruta.id, datos: { nombre: form.nombre.trim(), zona } }, alTerminar)
    else crear.mutate({ codigo: form.codigo.trim(), nombre: form.nombre.trim(), zona }, alTerminar)
  }
  const mostrar = (k: keyof FormRuta) =>
    intento && errores[k] ? (
      <span role="alert" className="text-xs font-normal text-bad">
        {errores[k]}
      </span>
    ) : null

  return (
    <Modal
      titulo={edicion ? 'Editar ruta' : 'Nueva ruta'}
      onCerrar={onCerrar}
      acciones={
        <>
          <Button onClick={onCerrar}>Cancelar</Button>
          <Button variant="primary" type="submit" form="form-ruta" disabled={mutacion.isPending}>
            {mutacion.isPending ? 'Guardando…' : edicion ? 'Guardar cambios' : 'Crear ruta'}
          </Button>
        </>
      }
    >
      <form id="form-ruta" onSubmit={enviar} noValidate className="flex flex-col gap-3">
        {mutacion.isError && <AlertBanner>{textoErrorRuta(mutacion.error)}</AlertBanner>}
        <Campo etiqueta="Código">
          <input
            value={form.codigo}
            disabled={edicion}
            onChange={(e) => set('codigo', e.target.value)}
            className={CLASE_INPUT}
            maxLength={20}
          />
          {mostrar('codigo')}
        </Campo>
        {edicion ? (
          <p className="text-xs text-muted">El código no cambia: el ETL identifica la ruta por él.</p>
        ) : (
          <p className="text-xs text-muted">Se guarda en mayúsculas y no podrá modificarse.</p>
        )}
        <Campo etiqueta="Nombre">
          <input value={form.nombre} onChange={(e) => set('nombre', e.target.value)} className={CLASE_INPUT} />
          {mostrar('nombre')}
        </Campo>
        <Campo etiqueta="Zona (opcional)">
          <input value={form.zona} onChange={(e) => set('zona', e.target.value)} className={CLASE_INPUT} maxLength={100} />
          {mostrar('zona')}
        </Campo>
      </form>
    </Modal>
  )
}

function InsigniaReparto({ ruta }: { ruta: RutaAdminOut }) {
  if (ruta.integrantes === 0)
    return <span className="rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-muted">Sin equipo</span>
  return (
    <span
      data-suma-100={ruta.equipo_completo ? 'si' : 'no'}
      className={`num rounded-full px-2 py-0.5 text-xs font-medium ${ruta.equipo_completo ? 'bg-good/10 text-good' : 'bg-bad/10 text-bad'}`}
    >
      {ruta.integrantes} integrantes · {ruta.suma_porcentaje} %
    </span>
  )
}

/** Rutas: alta, edición, activación/desactivación y acceso al equipo de cada ruta (M02). */
export function RoutesAdminView() {
  const { can } = usePermissions()
  const puedeGestionar = can('catalogos:gestionar')
  const [mostrarInactivas, setMostrarInactivas] = useState(false)
  const [modal, setModal] = useState<{ ruta: RutaAdminOut | null } | null>(null)
  const rutas = useRutasAdmin()
  const incompletos = useEquiposIncompletos()
  const desalineadas = useRutasDesalineadas()
  const { desactivar, activar } = useRutaActions()
  const visibles = (rutas.data ?? []).filter((r) => mostrarInactivas || r.activa)
  const error = desactivar.error ?? activar.error

  return (
    <div className="flex flex-col gap-4">
      <PestanasRutas />
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Rutas y equipos</h1>
          <p className="text-sm text-muted">Catálogo de rutas y personal que integra cada una.</p>
        </div>
        {puedeGestionar && (
          <Button variant="primary" onClick={() => setModal({ ruta: null })}>
            + Nueva ruta
          </Button>
        )}
      </header>

      <Card>
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={mostrarInactivas} onChange={(e) => setMostrarInactivas(e.target.checked)} />
          Mostrar rutas inactivas
        </label>
        {error && <AlertBanner>{textoErrorRuta(error)}</AlertBanner>}
        {rutas.isPending && <Cargando texto="Cargando rutas…" />}
        {rutas.isError && <AlertBanner>{mensajeError(rutas.error)}</AlertBanner>}
        {rutas.data && visibles.length === 0 && <EmptyState titulo="Sin rutas" detalle="No hay rutas para mostrar." />}
        {visibles.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <caption className="sr-only">Rutas</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-2 pr-3">Ruta</th>
                  <th className="py-2 pr-3">Zona</th>
                  <th className="py-2 pr-3">Equipo vigente</th>
                  <th className="py-2 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {visibles.map((r) => (
                  <tr key={r.id} className="border-b border-line align-top last:border-0">
                    <td className="py-2 pr-3">
                      {r.nombre} <span className="font-mono text-xs text-muted">{r.codigo}</span>
                      {!r.activa && (
                        <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-muted">Inactiva</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs">{r.zona ?? '—'}</td>
                    <td className="py-2 pr-3">
                      <InsigniaReparto ruta={r} />
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        <Link
                          to={`/catalogos/rutas/${r.id}/equipo`}
                          className="inline-flex items-center rounded-md border border-line bg-panel px-3.5 py-2 text-sm font-medium hover:bg-surface"
                          aria-label={`Equipo de ${r.codigo}`}
                        >
                          Equipo
                        </Link>
                        {puedeGestionar && (
                          <Button onClick={() => setModal({ ruta: r })} aria-label={`Editar ${r.codigo}`}>
                            Editar
                          </Button>
                        )}
                        {puedeGestionar && r.activa && (
                          <Button variant="danger" disabled={desactivar.isPending} onClick={() => desactivar.mutate(r.id)} aria-label={`Desactivar ${r.codigo}`}>
                            Desactivar
                          </Button>
                        )}
                        {puedeGestionar && !r.activa && (
                          <Button disabled={activar.isPending} onClick={() => activar.mutate(r.id)} aria-label={`Activar ${r.codigo}`}>
                            Activar
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card titulo="Rutas con equipo incompleto">
        {incompletos.isError && <AlertBanner>{mensajeError(incompletos.error)}</AlertBanner>}
        {incompletos.data && incompletos.data.length === 0 && (
          <p className="text-sm text-good">Todas las rutas activas tienen vendedor y reparto de 100 %.</p>
        )}
        <ul className="flex flex-col gap-1 text-sm">
          {incompletos.data?.map((r) => (
            <li key={r.ruta_id}>
              <Link to={`/catalogos/rutas/${r.ruta_id}/equipo`} className="text-brand">
                {r.nombre} <span className="font-mono text-xs">{r.codigo}</span>
              </Link>{' '}
              <span className="text-xs text-muted">
                — {r.motivos.map((m) => MOTIVO[m] ?? m).join(', ')} (suma {r.suma_porcentaje} %)
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card titulo="Rutas con vendedor desalineado">
        <p className="mb-2 text-xs text-muted">
          El vendedor de la ruta (usuario) y el vendedor del equipo (empleado) son dos fuentes distintas; aquí se listan las que
          no coinciden. No se sincronizan automáticamente.
        </p>
        {desalineadas.isError && <AlertBanner>{mensajeError(desalineadas.error)}</AlertBanner>}
        {desalineadas.data && desalineadas.data.length === 0 && (
          <p className="text-sm text-good">Sin diferencias entre ambas fuentes.</p>
        )}
        <ul className="flex flex-col gap-1 text-sm">
          {desalineadas.data?.map((r) => (
            <li key={r.ruta_id}>
              {r.nombre} <span className="font-mono text-xs">{r.codigo}</span>
              <span className="text-xs text-muted">
                {' '}
                — equipo: {r.empleado_vendedor}; usuario de la ruta: {r.vendedor_id_ruta ? 'asignado' : 'sin asignar'}; usuario del
                empleado: {r.usuario_id_empleado ? 'vinculado' : 'sin vincular'}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      {modal && <ModalRuta key={modal.ruta?.id ?? 'nueva'} ruta={modal.ruta} onCerrar={() => setModal(null)} />}
    </div>
  )
}
