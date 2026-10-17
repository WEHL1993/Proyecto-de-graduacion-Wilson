import { useMemo, useState } from 'react'
import { Button } from '../common/Button'
import { Card } from '../common/Card'
import { AlertBanner, Cargando } from '../feedback/feedback'
import { useMatriz, useRbacActions } from '../../hooks/useRbac'
import type { RolMatriz } from '../../types'
import { mensajeError } from '../../utils/errors'
import { RolBadge } from './RolBadge'

type Borrador = Record<number, string[]>

const igual = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x))

/** Matriz permisos × roles leída y guardada en las tablas `roles_permisos` (ADR-19). */
export function MatrizPermisosPanel() {
  const matriz = useMatriz()
  const { guardarPermisos, actualizarRol } = useRbacActions()
  const [borrador, setBorrador] = useState<Borrador>({})
  const [errores, setErrores] = useState<string[]>([])
  const [guardando, setGuardando] = useState(false)

  const roles = matriz.data?.roles ?? []
  const permisos = matriz.data?.permisos ?? []
  const pantallas = matriz.data?.pantallas ?? []

  const efectivo = (r: RolMatriz) => borrador[r.id] ?? r.permisos
  const cambios = useMemo(
    () =>
      roles
        .filter((r) => !r.es_sistema && borrador[r.id] && !igual(borrador[r.id], r.permisos))
        .map((r) => ({
          rol: r,
          altas: borrador[r.id].filter((p) => !r.permisos.includes(p)),
          bajas: r.permisos.filter((p) => !borrador[r.id].includes(p)),
        })),
    [roles, borrador],
  )

  const porModulo = useMemo(() => {
    const grupos = new Map<string, typeof permisos>()
    for (const p of permisos) grupos.set(p.modulo, [...(grupos.get(p.modulo) ?? []), p])
    return [...grupos.entries()]
  }, [permisos])

  const alternar = (r: RolMatriz, codigo: string) => {
    const actual = efectivo(r)
    const nuevo = actual.includes(codigo) ? actual.filter((c) => c !== codigo) : [...actual, codigo]
    setBorrador((b) => ({ ...b, [r.id]: nuevo }))
  }

  const guardar = async () => {
    setErrores([])
    setGuardando(true)
    const fallos: string[] = []
    for (const { rol } of cambios) {
      try {
        await guardarPermisos.mutateAsync({ rolId: rol.id, permisos: borrador[rol.id] })
        setBorrador((b) => {
          const resto = { ...b }
          delete resto[rol.id]
          return resto
        })
      } catch (e) {
        fallos.push(`${rol.nombre}: ${mensajeError(e)}`)
      }
    }
    setErrores(fallos)
    setGuardando(false)
  }

  if (matriz.isLoading) return <Cargando texto="Cargando matriz de permisos…" />
  if (matriz.isError) return <AlertBanner>{mensajeError(matriz.error)}</AlertBanner>

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <p className="mb-3 text-sm text-muted">
          Marque qué permisos tiene cada rol. Los cambios se guardan en la base de datos y rigen de inmediato para todos los
          usuarios del rol. El rol Administrador es del sistema y no se edita.
        </p>
        {actualizarRol.isError && <AlertBanner>{mensajeError(actualizarRol.error)}</AlertBanner>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Matriz de permisos por rol</caption>
            <thead>
              <tr className="text-left text-xs">
                <th className="min-w-56 py-2 pr-3 text-muted">Permiso</th>
                {roles.map((r) => (
                  <th key={r.id} scope="col" className="px-2 py-2 text-center align-bottom">
                    <RolBadge rol={r.nombre} color={r.color} inactivo={!r.activo} />
                    <div className="mt-1 font-normal text-muted">
                      {r.total_usuarios} usuario{r.total_usuarios === 1 ? '' : 's'}
                    </div>
                    {r.es_sistema ? (
                      <div className="mt-1 font-normal text-muted">Sistema</div>
                    ) : (
                      <button
                        type="button"
                        role="switch"
                        aria-checked={r.activo}
                        aria-label={`${r.activo ? 'Desactivar' : 'Activar'} rol ${r.nombre}`}
                        disabled={actualizarRol.isPending}
                        onClick={() => actualizarRol.mutate({ rolId: r.id, datos: { activo: !r.activo } })}
                        className={`relative mt-1 h-5 w-9 rounded-full transition disabled:opacity-50 ${r.activo ? 'bg-good' : 'bg-line'}`}
                      >
                        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${r.activo ? 'left-4' : 'left-0.5'}`} />
                      </button>
                    )}
                  </th>
                ))}
              </tr>
              <tr className="text-left text-xs">
                <th className="py-2 pr-3 font-normal text-muted">Pantalla de inicio</th>
                {roles.map((r) => (
                  <td key={r.id} className="px-2 py-1 text-center">
                    <select
                      aria-label={`Pantalla de inicio de ${r.nombre}`}
                      value={r.pantalla_inicio ?? ''}
                      disabled={r.es_sistema || actualizarRol.isPending}
                      onChange={(ev) =>
                        actualizarRol.mutate({ rolId: r.id, datos: { pantalla_inicio: ev.target.value || null } })
                      }
                      className="max-w-32 rounded border border-line bg-panel px-1 py-0.5 text-xs"
                    >
                      <option value="">Automática</option>
                      {pantallas.map((p) => (
                        <option key={p.clave} value={p.clave}>
                          {p.etiqueta}
                        </option>
                      ))}
                    </select>
                  </td>
                ))}
              </tr>
            </thead>
            <tbody>
              {porModulo.map(([modulo, lista]) => (
                <ModuloFilas key={modulo} modulo={modulo} roles={roles} lista={lista} efectivo={efectivo} alternar={alternar} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {cambios.length > 0 && (
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Cambios sin guardar</h2>
          <ul className="mb-3 space-y-1 text-sm">
            {cambios.map(({ rol, altas, bajas }) => (
              <li key={rol.id}>
                <strong>{rol.nombre}</strong>
                {altas.length > 0 && <span className="ml-2 text-good">+ {altas.join(', ')}</span>}
                {bajas.length > 0 && <span className="ml-2 text-bad">− {bajas.join(', ')}</span>}
              </li>
            ))}
          </ul>
          {errores.map((e) => (
            <AlertBanner key={e}>{e}</AlertBanner>
          ))}
          <div className="flex gap-2">
            <Button variant="primary" disabled={guardando} onClick={() => void guardar()}>
              {guardando ? 'Guardando…' : `Guardar cambios (${cambios.length})`}
            </Button>
            <Button disabled={guardando} onClick={() => setBorrador({})}>
              Descartar
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}

interface FilasProps {
  modulo: string
  roles: RolMatriz[]
  lista: { id: number; codigo: string; descripcion?: string | null; activo: boolean }[]
  efectivo: (r: RolMatriz) => string[]
  alternar: (r: RolMatriz, codigo: string) => void
}

function ModuloFilas({ modulo, roles, lista, efectivo, alternar }: FilasProps) {
  return (
    <>
      <tr className="bg-surface">
        <th colSpan={roles.length + 1} scope="colgroup" className="py-1 pl-2 text-left text-xs font-semibold uppercase text-muted">
          {modulo.replace(/_/g, ' ')}
        </th>
      </tr>
      {lista.map((p) => (
        <tr key={p.id} className="border-t border-line">
          <th scope="row" className="py-1.5 pr-3 text-left font-normal" title={p.descripcion ?? undefined}>
            <code className="text-xs">{p.codigo}</code>
          </th>
          {roles.map((r) => (
            <td key={r.id} className="px-2 py-1.5 text-center">
              <input
                type="checkbox"
                aria-label={`${r.nombre} · ${p.codigo}`}
                checked={efectivo(r).includes(p.codigo)}
                disabled={r.es_sistema}
                onChange={() => alternar(r, p.codigo)}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}
