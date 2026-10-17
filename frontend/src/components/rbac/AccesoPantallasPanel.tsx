import { useState } from 'react'
import { Card, Campo, CLASE_INPUT } from '../common/Card'
import { AlertBanner, Cargando } from '../feedback/feedback'
import { useAccesoUsuario, useMatriz } from '../../hooks/useRbac'
import { useUsuarios } from '../../hooks/useUsers'
import { mensajeError } from '../../utils/errors'
import { RolBadge } from './RolBadge'

/** Pantallas autorizadas por rol y por usuario, calculadas desde la BD. */
export function AccesoPantallasPanel() {
  const matriz = useMatriz()
  const usuarios = useUsuarios({ q: '', rol: '', activo: undefined })
  const [usuarioId, setUsuarioId] = useState('')
  const acceso = useAccesoUsuario(usuarioId)

  if (matriz.isLoading) return <Cargando texto="Cargando pantallas…" />
  if (matriz.isError) return <AlertBanner>{mensajeError(matriz.error)}</AlertBanner>
  const roles = matriz.data?.roles ?? []
  const pantallas = matriz.data?.pantallas ?? []

  // Un rol ve una pantalla si está activo y tiene ALGUNO de sus permisos.
  const ve = (rolPermisos: string[], activo: boolean, requeridos: string[]) =>
    activo && requeridos.some((p) => rolPermisos.includes(p))

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-2 text-sm font-semibold">Pantallas por rol</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Pantallas autorizadas por rol</caption>
            <thead>
              <tr className="text-xs">
                <th className="min-w-56 py-2 pr-3 text-left text-muted">Pantalla</th>
                {roles.map((r) => (
                  <th key={r.id} scope="col" className="px-2 py-2 text-center">
                    <RolBadge rol={r.nombre} color={r.color} inactivo={!r.activo} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pantallas.map((p) => (
                <tr key={p.clave} className="border-t border-line">
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                    {p.etiqueta}
                    <span className="ml-2 text-xs text-muted">{p.ruta}</span>
                  </th>
                  {roles.map((r) => {
                    const si = ve(r.permisos, r.activo, p.permisos)
                    return (
                      <td key={r.id} className="px-2 py-1.5 text-center" aria-label={`${r.nombre} · ${p.etiqueta}: ${si ? 'sí' : 'no'}`}>
                        {si ? <span className="text-good">✔</span> : <span className="text-muted">—</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <h2 className="mb-2 text-sm font-semibold">Ver como usuario</h2>
        <Campo etiqueta="Usuario">
          <select value={usuarioId} onChange={(e) => setUsuarioId(e.target.value)} className={`${CLASE_INPUT} w-72`}>
            <option value="">Seleccione un usuario…</option>
            {usuarios.data?.usuarios.map((u) => (
              <option key={u.id} value={u.id}>
                {u.nombre_completo} · {u.email}
              </option>
            ))}
          </select>
        </Campo>
        {acceso.isLoading && <Cargando texto="Calculando acceso…" />}
        {acceso.isError && <AlertBanner>{mensajeError(acceso.error)}</AlertBanner>}
        {acceso.data && (
          <div className="mt-3">
            <p className="mb-2 text-sm">
              Roles activos: {acceso.data.roles.length ? acceso.data.roles.join(', ') : <span className="text-muted">ninguno</span>}
              {!acceso.data.activo && <span className="ml-2 text-bad">(cuenta inactiva: sin acceso)</span>}
            </p>
            <ul className="grid gap-1 sm:grid-cols-2">
              {acceso.data.pantallas.map((p) => (
                <li key={p.clave} className={`rounded border border-line px-2 py-1 text-sm ${p.autorizada ? '' : 'opacity-50'}`}>
                  <span className={p.autorizada ? 'text-good' : 'text-muted'}>{p.autorizada ? '✔' : '—'}</span> {p.etiqueta}
                  {p.autorizada && <span className="ml-2 text-xs text-muted">vía {p.via_permisos.join(', ')}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  )
}
