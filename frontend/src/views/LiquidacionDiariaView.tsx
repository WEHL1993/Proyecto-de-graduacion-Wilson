import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../app/providers/AuthProvider'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import {
  useAnularLiquidacion,
  useCerrarLiquidacion,
  useConfigLiquidacion,
  useCorregirLiquidacion,
  useGuardarLiquidacion,
  usePrecarga,
} from '../hooks/useLiquidaciones'
import { listarRutas } from '../services/catalogApi'
import type { LiquidacionResponse } from '../types'
import { mensajeError } from '../utils/errors'
import { fmt, hoyISO } from '../utils/format'
import {
  PAGOS_VACIOS,
  aSolicitud,
  diferenciaCaja,
  diferenciaFila,
  efectivoEsperado,
  esMontoValido,
  estadoFila,
  filasDeLiquidacion,
  filasDePrecarga,
  pagosDeLiquidacion,
  semaforoCaja,
  totalPagos,
  totalesUnidades,
  validar,
  ventaTotal,
} from '../utils/liquidacion'
import type { FilaForm, PagosForm } from '../utils/liquidacion'

const UMBRAL_POR_DEFECTO = 10
const Q = (n: number) => `Q ${fmt(n)}`

type Accion = 'cerrar' | 'corregir' | 'anular' | null
type Aviso = { tipo: 'exito' | 'info'; texto: string; detalles?: string[] } | null

const FILA_ESTILO = { cuadra: 'text-good', falta: 'text-warn', excede: 'text-bad' } as const
const FILA_ICONO = { cuadra: '🟢 Cuadra', falta: '🟡 Faltan', excede: '🔴 Excede' } as const
const CAJA_ESTILO = { verde: 'text-good', ambar: 'text-warn', rojo: 'text-bad' } as const
const CAJA_ICONO = { verde: '🟢', ambar: '🟡', rojo: '🔴' } as const

/** Liquidación del día por ruta y vendedor, en dos pasos: unidades y dinero (ADR-14). */
export function LiquidacionDiariaView() {
  const { can } = useAuth()
  const [fecha, setFecha] = useState(hoyISO())
  const [rutaId, setRutaId] = useState('')
  const [paso, setPaso] = useState<1 | 2>(1)
  const [filas, setFilas] = useState<FilaForm[]>([])
  const [pagos, setPagos] = useState<PagosForm>(PAGOS_VACIOS)
  const [observaciones, setObservaciones] = useState('')
  const [existente, setExistente] = useState<LiquidacionResponse | null>(null)
  const [accion, setAccion] = useState<Accion>(null)
  const [motivo, setMotivo] = useState('')
  const [aviso, setAviso] = useState<Aviso>(null)

  const rutas = useQuery({ queryKey: ['rutas'], queryFn: listarRutas })
  const precarga = usePrecarga(fecha, rutaId)
  const config = useConfigLiquidacion(can('liquidaciones:leer'))
  const guardar = useGuardarLiquidacion()
  const cerrar = useCerrarLiquidacion()
  const corregir = useCorregirLiquidacion()
  const anular = useAnularLiquidacion()

  const umbral = Number(config.data?.umbral_diferencia_caja ?? UMBRAL_POR_DEFECTO)
  const cerrada = existente?.estado === 'cerrada'

  // Al cambiar fecha/ruta se (re)carga el formulario: lo despachado o la liquidación vigente.
  useEffect(() => {
    const d = precarga.data
    if (!d) return
    const despachado = d.carga_id ? new Map(d.lineas.map((l) => [l.producto_id, Number(l.cantidad_cargada)])) : null
    if (d.liquidacion) {
      setExistente(d.liquidacion)
      setFilas(filasDeLiquidacion(d.liquidacion, despachado))
      setPagos(pagosDeLiquidacion(d.liquidacion))
      setObservaciones(d.liquidacion.observaciones ?? '')
    } else {
      setExistente(null)
      setFilas(filasDePrecarga(d.lineas, Boolean(d.carga_id)))
      setPagos(PAGOS_VACIOS)
      setObservaciones('')
    }
    setPaso(1)
    setAviso(null)
  }, [precarga.data])

  const validacion = useMemo(() => validar(filas, pagos), [filas, pagos])
  const unidades = useMemo(() => totalesUnidades(filas), [filas])
  const venta = ventaTotal(filas)
  const esperado = efectivoEsperado(pagos)
  const dif = diferenciaCaja(pagos)
  const semaforo = semaforoCaja(dif, umbral)
  const puedeGuardar = validacion.errores.length === 0
  const puedeCerrar = puedeGuardar && validacion.pendientes.length === 0

  const cambiarFila = (i: number, cambio: Partial<FilaForm>) =>
    setFilas((fs) => fs.map((f, j) => (j === i ? { ...f, ...cambio } : f)))
  const cambiarPago = (k: keyof PagosForm, v: string) => setPagos((p) => ({ ...p, [k]: v }))
  const solicitud = () => aSolicitud(fecha, rutaId, filas, pagos, observaciones)

  const adoptar = (r: LiquidacionResponse, texto: string) => {
    setExistente(r)
    setAviso({ tipo: 'exito', texto, detalles: r.advertencias })
    setAccion(null)
    setMotivo('')
  }

  const guardarBorrador = () =>
    guardar.mutate(solicitud(), { onSuccess: (r) => adoptar(r, 'Borrador guardado: aún no afecta al modelo.') })

  const confirmar = async () => {
    try {
      if (accion === 'cerrar') {
        const base = existente && existente.estado === 'borrador' ? existente : await guardar.mutateAsync(solicitud())
        const r = await cerrar.mutateAsync(base.id)
        adoptar(r, 'Liquidación cerrada: las ventas ya alimentan el modelo.')
      } else if (accion === 'corregir' && existente) {
        const r = await corregir.mutateAsync({ id: existente.id, cuerpo: solicitud(), motivo: motivo.trim() })
        adoptar(r, `Corrección registrada (versión ${r.version}).`)
      } else if (accion === 'anular' && existente) {
        await anular.mutateAsync({ id: existente.id, motivo: motivo.trim() })
        setExistente(null)
        setAccion(null)
        setMotivo('')
        setAviso({ tipo: 'info', texto: 'Liquidación anulada.' })
        void precarga.refetch()
      }
    } catch {
      /* el error se muestra desde la mutación correspondiente */
    }
  }

  const error = [guardar, cerrar, corregir, anular].find((m) => m.isError)
  const ocupado = guardar.isPending || cerrar.isPending || corregir.isPending || anular.isPending
  const motivoOk = motivo.trim().length >= 5

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Liquidación diaria de ventas</h1>
          <p className="text-sm text-muted">Registre por ruta lo cargado, vendido, devuelto y el dinero entregado al cierre del día.</p>
        </div>
        {existente && (
          <span className="rounded-full bg-brand/10 px-3 py-1 text-xs font-medium text-brand">
            {cerrada ? `Corrección · v${existente.version}` : `Borrador`}
          </span>
        )}
      </header>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Campo etiqueta="Fecha">
            <input type="date" max={hoyISO()} value={fecha} onChange={(e) => setFecha(e.target.value)} className={CLASE_INPUT} />
          </Campo>
          <Campo etiqueta="Ruta">
            <select aria-label="Ruta" value={rutaId} onChange={(e) => setRutaId(e.target.value)} className={CLASE_INPUT}>
              <option value="">Seleccione…</option>
              {rutas.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.codigo} · {r.nombre}
                </option>
              ))}
            </select>
          </Campo>
        </div>
      </Card>

      {!rutaId && <EmptyState titulo="Seleccione una ruta" detalle="Se precargará lo despachado ese día para que solo ingrese lo vendido, devuelto y el dinero." />}
      {rutaId && precarga.isLoading && <Cargando texto="Cargando datos del día…" />}
      {rutaId && precarga.isError && <AlertBanner>{mensajeError(precarga.error)}</AlertBanner>}
      {precarga.data?.advertencias?.map((a) => (
        <AlertBanner key={a} tipo="info">
          {a}
        </AlertBanner>
      ))}
      {aviso && (
        <AlertBanner tipo={aviso.tipo}>
          {aviso.texto}
          {!!aviso.detalles?.length && (
            <ul className="mt-1 list-disc pl-5">
              {aviso.detalles.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </AlertBanner>
      )}
      {error && <AlertBanner>{mensajeError(error.error)}</AlertBanner>}

      {precarga.data && !filas.length && <EmptyState titulo="Sin presentaciones" detalle="La ruta no tiene carga despachada ni historial de ventas para precargar." />}

      {!!filas.length && (
        <>
          <nav aria-label="Pasos" className="flex gap-2 text-sm">
            <Button variant={paso === 1 ? 'primary' : 'secondary'} onClick={() => setPaso(1)}>
              1 · Unidades
            </Button>
            <Button variant={paso === 2 ? 'primary' : 'secondary'} onClick={() => setPaso(2)}>
              2 · Dinero
            </Button>
          </nav>

          {paso === 1 ? (
            <Card titulo="Unidades por presentación">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <caption className="sr-only">Unidades por presentación</caption>
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-muted">
                      <th className="py-2 pr-2">Presentación</th>
                      <th className="px-1 text-right">Cargado</th>
                      <th className="px-1 text-right">Vendido</th>
                      <th className="px-1 text-right">Devuelto</th>
                      <th className="px-1 text-right">Merma</th>
                      <th className="px-1 text-center">Agotado</th>
                      <th className="px-1">Cuadre</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas.map((f, i) => {
                      const estado = estadoFila(f)
                      const pideJustificacion = f.despachada !== null && Number(f.cargada || 0) !== f.despachada
                      return (
                        <tr key={f.producto_id} className="border-b border-line align-top">
                          <td className="py-1.5 pr-2">
                            <p className="font-medium">{f.sku}</p>
                            <p className="text-xs text-muted">{f.nombre}</p>
                            {pideJustificacion && (
                              <input
                                aria-label={`Justificación de lo cargado ${f.sku}`}
                                placeholder={`Despachado: ${f.despachada}. Justifique`}
                                value={f.justificacion}
                                onChange={(e) => cambiarFila(i, { justificacion: e.target.value })}
                                className={`${CLASE_INPUT} mt-1 w-full text-xs`}
                              />
                            )}
                          </td>
                          {(['cargada', 'vendida', 'devuelta', 'merma'] as const).map((k) => (
                            <td key={k} className="px-1 py-1.5">
                              <input
                                inputMode="decimal"
                                aria-label={`${k === 'cargada' ? 'Cargado' : k === 'vendida' ? 'Vendido' : k === 'devuelta' ? 'Devuelto' : 'Merma'} ${f.sku}`}
                                aria-invalid={!esMontoValido(f[k])}
                                value={f[k]}
                                onChange={(e) => cambiarFila(i, { [k]: e.target.value })}
                                className={`${CLASE_INPUT} num w-20 text-right ${esMontoValido(f[k]) ? '' : 'border-bad'}`}
                              />
                            </td>
                          ))}
                          <td className="px-1 py-1.5 text-center">
                            <input
                              type="checkbox"
                              aria-label={`Agotado ${f.sku}`}
                              checked={f.agotado}
                              onChange={(e) => cambiarFila(i, { agotado: e.target.checked })}
                            />
                          </td>
                          <td className={`num whitespace-nowrap px-1 py-1.5 text-xs font-medium ${FILA_ESTILO[estado]}`}>
                            {FILA_ICONO[estado]}
                            {estado !== 'cuadra' && ` ${Math.abs(diferenciaFila(f))}`}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot>
                    <tr className="num font-semibold">
                      <td className="py-2">Totales</td>
                      <td className="px-1 text-right" data-testid="total-cargadas">{unidades.cargadas}</td>
                      <td className="px-1 text-right" data-testid="total-vendidas">{unidades.vendidas}</td>
                      <td className="px-1 text-right" data-testid="total-devueltas">{unidades.devueltas}</td>
                      <td className="px-1 text-right">{unidades.merma}</td>
                      <td colSpan={2} className="px-1 text-xs font-normal text-muted">
                        Devolución esperada: {unidades.devueltas} u (la procesa Inventario)
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </Card>
          ) : (
            <Card titulo="Dinero del día">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div className="rounded-md border border-line bg-surface p-3">
                  <p className="text-xs text-muted">Venta total (calculada)</p>
                  <p className="num text-lg font-semibold" data-testid="venta-total">{Q(venta)}</p>
                </div>
                {(
                  [
                    ['efectivo', 'Efectivo'],
                    ['transferencia', 'Transferencia'],
                    ['credito', 'Crédito'],
                    ['cobro_saldos', 'Cobro de saldos anteriores'],
                    ['gastos', 'Gastos de ruta'],
                    ['efectivo_entregado', 'Efectivo entregado'],
                  ] as const
                ).map(([k, etiqueta]) => (
                  <Campo key={k} etiqueta={etiqueta}>
                    <input
                      inputMode="decimal"
                      aria-label={etiqueta}
                      aria-invalid={!esMontoValido(pagos[k])}
                      value={pagos[k]}
                      onChange={(e) => cambiarPago(k, e.target.value)}
                      className={`${CLASE_INPUT} num text-right ${esMontoValido(pagos[k]) ? '' : 'border-bad'}`}
                    />
                  </Campo>
                ))}
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted">Venta − (efectivo + transferencia + crédito)</dt>
                  <dd className={`num font-semibold ${venta === totalPagos(pagos) ? 'text-good' : 'text-bad'}`} data-testid="dif-venta">
                    {Q(venta - totalPagos(pagos))}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Efectivo esperado</dt>
                  <dd className="num font-semibold" data-testid="efectivo-esperado">{Q(esperado)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Diferencia de caja (umbral {Q(umbral)})</dt>
                  <dd className={`num font-semibold ${CAJA_ESTILO[semaforo]}`} data-testid="dif-caja">
                    {CAJA_ICONO[semaforo]} {Q(dif)}
                  </dd>
                </div>
              </dl>
              <div className="mt-4">
                <Campo etiqueta="Observaciones">
                  <textarea value={observaciones} onChange={(e) => setObservaciones(e.target.value)} rows={2} maxLength={1000} className={CLASE_INPUT} />
                </Campo>
              </div>
            </Card>
          )}

          {!!validacion.errores.length && (
            <AlertBanner>
              <ul className="list-disc pl-5">
                {validacion.errores.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </AlertBanner>
          )}
          {!validacion.errores.length && !!validacion.pendientes.length && (
            <AlertBanner tipo="info">
              Para cerrar falta cuadrar:
              <ul className="list-disc pl-5">
                {validacion.pendientes.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </AlertBanner>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            {existente && existente.estado !== 'anulada' && can('liquidaciones:corregir') && (
              <Button variant="danger" disabled={ocupado} onClick={() => setAccion('anular')}>
                Anular
              </Button>
            )}
            {cerrada ? (
              can('liquidaciones:corregir') && (
                <Button variant="primary" disabled={!puedeCerrar || ocupado} onClick={() => setAccion('corregir')}>
                  Corregir liquidación
                </Button>
              )
            ) : (
              <>
                {can('liquidaciones:registrar') && (
                  <Button disabled={!puedeGuardar || ocupado} onClick={guardarBorrador}>
                    Guardar borrador
                  </Button>
                )}
                {can('liquidaciones:cerrar') && (
                  <Button variant="primary" disabled={!puedeCerrar || ocupado} onClick={() => setAccion('cerrar')}>
                    Cerrar liquidación
                  </Button>
                )}
              </>
            )}
          </div>
        </>
      )}

      {accion && (
        <Modal
          titulo={accion === 'cerrar' ? 'Cerrar liquidación' : accion === 'corregir' ? 'Corregir liquidación' : 'Anular liquidación'}
          onCerrar={() => setAccion(null)}
          acciones={
            <>
              <Button onClick={() => setAccion(null)}>Cancelar</Button>
              <Button
                variant={accion === 'anular' ? 'danger' : 'primary'}
                disabled={ocupado || (accion !== 'cerrar' && !motivoOk)}
                onClick={confirmar}
              >
                Confirmar
              </Button>
            </>
          }
        >
          {accion === 'cerrar' && (
            <p>
              Al cerrar, las ventas de <strong>{unidades.vendidas} unidades</strong> ({Q(venta)}) se guardan en el histórico y{' '}
              <strong>alimentan el modelo predictivo</strong>: rellenan la demanda real y el monitoreo de precisión. Podrá corregirla después, dejando auditoría.
            </p>
          )}
          {accion === 'corregir' && <p className="mb-2">La corrección crea una nueva versión, recalcula la demanda real y deja auditoría.</p>}
          {accion === 'anular' && <p className="mb-2">Si estaba cerrada, se revierte su efecto en el histórico de ventas.</p>}
          {accion !== 'cerrar' && (
            <Campo etiqueta="Motivo (mínimo 5 caracteres)">
              <input aria-label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} className={CLASE_INPUT} />
            </Campo>
          )}
        </Modal>
      )}
    </div>
  )
}
