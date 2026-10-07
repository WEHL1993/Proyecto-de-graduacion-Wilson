import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { usePermissions } from '../hooks/usePermissions'
import { useEmpleados, useEquipo, useRutaActions, useRutaAdmin } from '../hooks/useRoutesAdmin'
import type { EmpleadoOut, EquipoRutaOut, RolEnRuta } from '../types'
import { mensajeError } from '../utils/errors'
import { hoyISO } from '../utils/format'

// ---------------------------------------------------------------- reglas del formulario
export interface FilaEquipo {
  empleado_id: string
  rol_en_ruta: RolEnRuta
  porcentaje: string
}

export const FILA_VACIA: FilaEquipo = { empleado_id: '', rol_en_ruta: 'auxiliar', porcentaje: '' }

export const ETIQUETA_ROL: Record<RolEnRuta, string> = {
  vendedor: 'Vendedor',
  chofer: 'Chofer',
  auxiliar: 'Auxiliar',
}

const TOTAL_CENTAVOS = 10_000

/** Porcentaje en centésimas (35,5 → 3550) sin errores de coma flotante; `null` si no es válido. */
export function aCentavos(valor: string): number | null {
  const t = valor.trim().replace(',', '.')
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null
  return Math.round(Number(t) * 100)
}

export const sumaCentavos = (filas: FilaEquipo[]): number =>
  filas.reduce((acc, f) => acc + (aCentavos(f.porcentaje) ?? 0), 0)

export const textoSuma = (centavos: number): string => (centavos / 100).toFixed(2)

/** Errores del equipo; vacío = se puede guardar. El servidor es la autoridad (`EQUIPO_NO_SUMA_100`). */
export function validarEquipo(filas: FilaEquipo[]): string[] {
  const errores: string[] = []
  if (filas.length === 0) return ['Agregue al menos un integrante.']
  if (filas.some((f) => !f.empleado_id)) errores.push('Seleccione un empleado en cada fila.')
  const ids = filas.map((f) => f.empleado_id).filter(Boolean)
  if (new Set(ids).size !== ids.length) errores.push('Un empleado no puede repetirse en el equipo.')
  if (filas.filter((f) => f.rol_en_ruta === 'vendedor').length > 1)
    errores.push('La ruta admite como máximo un vendedor.')
  if (filas.some((f) => aCentavos(f.porcentaje) === null))
    errores.push('Cada porcentaje debe ser un número entre 0 y 100 con hasta 2 decimales.')
  else if (filas.some((f) => (aCentavos(f.porcentaje) ?? 0) > TOTAL_CENTAVOS))
    errores.push('Ningún porcentaje puede superar 100.')
  if (sumaCentavos(filas) !== TOTAL_CENTAVOS)
    errores.push(`Los porcentajes deben sumar exactamente 100,00 (suman ${textoSuma(sumaCentavos(filas))}).`)
  return errores
}

export const filasDesdeEquipo = (equipo: EquipoRutaOut): FilaEquipo[] =>
  equipo.integrantes.map((i) => ({
    empleado_id: i.empleado_id,
    rol_en_ruta: i.rol_en_ruta,
    porcentaje: String(i.porcentaje_reparto),
  }))

/** Indicador visible «suma 100 %»: verde al cuadrar, rojo con la diferencia. */
export function IndicadorSuma({ centavos }: { centavos: number }) {
  const ok = centavos === TOTAL_CENTAVOS
  return (
    <p
      role="status"
      aria-live="polite"
      data-suma-100={ok ? 'si' : 'no'}
      className={`num text-sm font-medium ${ok ? 'text-good' : 'text-bad'}`}
    >
      Suma de reparto: {textoSuma(centavos)} % {ok ? '✓ cuadra' : `· faltan ${textoSuma(TOTAL_CENTAVOS - centavos)} para 100,00`}
    </p>
  )
}

// ---------------------------------------------------------------- editor
function EditorEquipo({
  rutaId,
  equipo,
  empleados,
  puedeGestionar,
}: {
  rutaId: string
  equipo: EquipoRutaOut
  empleados: EmpleadoOut[]
  puedeGestionar: boolean
}) {
  const [filas, setFilas] = useState<FilaEquipo[]>(() => {
    const previas = filasDesdeEquipo(equipo)
    return previas.length ? previas : [{ ...FILA_VACIA, rol_en_ruta: 'vendedor' }]
  })
  const [desde, setDesde] = useState(hoyISO())
  const [intento, setIntento] = useState(false)
  const { guardarEquipo } = useRutaActions()
  const errores = validarEquipo(filas)
  const suma = sumaCentavos(filas)

  // Los empleados del equipo vigente que ya no están activos siguen apareciendo para no perder la fila.
  const opciones = [...empleados]
  for (const i of equipo.integrantes)
    if (!opciones.some((e) => e.id === i.empleado_id))
      opciones.push({ id: i.empleado_id, nombre_completo: i.nombre_completo, activo: false } as EmpleadoOut)

  const cambiar = (idx: number, parcial: Partial<FilaEquipo>) =>
    setFilas((fs) => fs.map((f, i) => (i === idx ? { ...f, ...parcial } : f)))

  const enviar = (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    if (errores.length) return
    guardarEquipo.mutate({
      rutaId,
      datos: {
        vigente_desde: desde,
        integrantes: filas.map((f) => ({
          empleado_id: f.empleado_id,
          rol_en_ruta: f.rol_en_ruta,
          porcentaje_reparto: (aCentavos(f.porcentaje)! / 100).toFixed(2),
        })),
      },
    })
  }

  return (
    <form onSubmit={enviar} noValidate className="flex flex-col gap-3">
      {guardarEquipo.isError && <AlertBanner>{mensajeError(guardarEquipo.error)}</AlertBanner>}
      {guardarEquipo.isSuccess && !guardarEquipo.isPending && (
        <p role="status" className="text-sm text-good">
          Equipo guardado. Las vigencias anteriores quedaron cerradas en el historial.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <caption className="sr-only">Integrantes del equipo de la ruta</caption>
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-2 pr-3">Empleado</th>
              <th className="py-2 pr-3">Rol en la ruta</th>
              <th className="py-2 pr-3 text-right">Reparto (%)</th>
              <th className="py-2 text-right">
                <span className="sr-only">Quitar</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f, idx) => (
              <tr key={idx} className="border-b border-line last:border-0">
                <td className="py-2 pr-3">
                  <select
                    aria-label={`Empleado ${idx + 1}`}
                    value={f.empleado_id}
                    disabled={!puedeGestionar}
                    onChange={(e) => cambiar(idx, { empleado_id: e.target.value })}
                    className={`${CLASE_INPUT} w-full`}
                  >
                    <option value="">Seleccione…</option>
                    {opciones.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.nombre_completo}
                        {e.activo ? '' : ' (baja)'}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-3">
                  <select
                    aria-label={`Rol ${idx + 1}`}
                    value={f.rol_en_ruta}
                    disabled={!puedeGestionar}
                    onChange={(e) => cambiar(idx, { rol_en_ruta: e.target.value as RolEnRuta })}
                    className={CLASE_INPUT}
                  >
                    {(Object.keys(ETIQUETA_ROL) as RolEnRuta[]).map((r) => (
                      <option key={r} value={r}>
                        {ETIQUETA_ROL[r]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-3 text-right">
                  <input
                    aria-label={`Porcentaje ${idx + 1}`}
                    inputMode="decimal"
                    value={f.porcentaje}
                    disabled={!puedeGestionar}
                    onChange={(e) => cambiar(idx, { porcentaje: e.target.value })}
                    className={`${CLASE_INPUT} num w-24 text-right`}
                  />
                </td>
                <td className="py-2 text-right">
                  {puedeGestionar && filas.length > 1 && (
                    <Button aria-label={`Quitar fila ${idx + 1}`} onClick={() => setFilas((fs) => fs.filter((_, i) => i !== idx))}>
                      Quitar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <IndicadorSuma centavos={suma} />
      {intento && errores.length > 0 && (
        <ul role="alert" className="list-disc pl-5 text-xs text-bad">
          {errores.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}

      {puedeGestionar && (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-end gap-3">
            <Button onClick={() => setFilas((fs) => [...fs, { ...FILA_VACIA }])}>+ Agregar integrante</Button>
            <Campo etiqueta="Vigente desde">
              <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className={CLASE_INPUT} />
            </Campo>
          </div>
          <Button variant="primary" type="submit" disabled={guardarEquipo.isPending}>
            {guardarEquipo.isPending ? 'Guardando…' : 'Guardar equipo'}
          </Button>
        </div>
      )}
    </form>
  )
}

// ---------------------------------------------------------------- vista
/** Equipo de una ruta: integrantes, rol, porcentaje de reparto (debe sumar 100) e historial. */
export function RouteTeamView() {
  const { rutaId = '' } = useParams()
  const { can } = usePermissions()
  const puedeGestionar = can('catalogos:gestionar')
  const ruta = useRutaAdmin(rutaId)
  const equipo = useEquipo(rutaId)
  const empleados = useEmpleados({ activo: true, limit: 200 })

  return (
    <div className="flex flex-col gap-4">
      <header>
        <Link to="/catalogos/rutas" className="text-xs text-brand">
          ← Rutas
        </Link>
        <h1 className="text-lg font-semibold">
          Equipo de la ruta {ruta.data ? `${ruta.data.codigo} · ${ruta.data.nombre}` : ''}
        </h1>
        <p className="text-sm text-muted">
          El reparto vigente debe sumar 100 %. Al guardar, el equipo anterior se cierra (no se borra).
        </p>
      </header>

      <Card titulo="Equipo vigente">
        {(equipo.isPending || empleados.isPending) && <Cargando texto="Cargando equipo…" />}
        {equipo.isError && <AlertBanner>{mensajeError(equipo.error)}</AlertBanner>}
        {empleados.isError && <AlertBanner>{mensajeError(empleados.error)}</AlertBanner>}
        {equipo.data && empleados.data && (
          <EditorEquipo
            key={rutaId}
            rutaId={rutaId}
            equipo={equipo.data}
            empleados={empleados.data.items}
            puedeGestionar={puedeGestionar}
          />
        )}
      </Card>

      <Card titulo="Historial de vigencias">
        {equipo.data && equipo.data.historial.length === 0 && (
          <EmptyState titulo="Sin historial" detalle="Aún no se ha reemplazado el equipo de esta ruta." />
        )}
        {!!equipo.data?.historial.length && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <caption className="sr-only">Integrantes anteriores de la ruta</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-2 pr-3">Empleado</th>
                  <th className="py-2 pr-3">Rol</th>
                  <th className="py-2 pr-3 text-right">Reparto</th>
                  <th className="py-2">Vigencia</th>
                </tr>
              </thead>
              <tbody>
                {equipo.data.historial.map((h, i) => (
                  <tr key={`${h.empleado_id}-${h.vigente_desde}-${i}`} className="border-b border-line last:border-0">
                    <td className="py-2 pr-3">{h.nombre_completo}</td>
                    <td className="py-2 pr-3">{ETIQUETA_ROL[h.rol_en_ruta]}</td>
                    <td className="num py-2 pr-3 text-right">{h.porcentaje_reparto} %</td>
                    <td className="num py-2 text-xs">
                      {h.vigente_desde} → {h.vigente_hasta ?? 'vigente'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
