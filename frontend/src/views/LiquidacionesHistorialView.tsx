import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { useListadoLiquidaciones, useLiquidacionDetalle } from '../hooks/useLiquidaciones'
import { listarRutas } from '../services/catalogApi'
import type { EstadoLiquidacion } from '../types'
import { mensajeError } from '../utils/errors'
import { fmt, fmtFecha, fmtInt } from '../utils/format'

const TAMANO_PAGINA = 15
const ESTILO_ESTADO: Record<EstadoLiquidacion, string> = {
  cerrada: 'bg-good/10 text-good',
  borrador: 'bg-surface text-muted',
  anulada: 'bg-bad/10 text-bad',
}
const Q = (v: string | number) => `Q ${fmt(v)}`

/** Historial de liquidaciones con su cuadre de caja (Administrador y Gerente). */
export function LiquidacionesHistorialView() {
  const [pagina, setPagina] = useState(0)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [rutaId, setRutaId] = useState('')
  const [estado, setEstado] = useState<EstadoLiquidacion | ''>('')
  const [detalleId, setDetalleId] = useState<string | null>(null)

  const rutas = useQuery({ queryKey: ['rutas'], queryFn: listarRutas })
  const listado = useListadoLiquidaciones({ desde, hasta, ruta_id: rutaId, estado, limit: TAMANO_PAGINA, offset: pagina * TAMANO_PAGINA })
  const total = listado.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / TAMANO_PAGINA))
  const filtrar = <T,>(set: (v: T) => void) => (v: T) => {
    set(v)
    setPagina(0)
  }

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-lg font-semibold">Historial de liquidaciones</h1>
        <p className="text-sm text-muted">Consulte lo liquidado por ruta, el cuadre de caja y las correcciones.</p>
      </header>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Campo etiqueta="Desde">
            <input type="date" value={desde} onChange={(e) => filtrar(setDesde)(e.target.value)} className={CLASE_INPUT} />
          </Campo>
          <Campo etiqueta="Hasta">
            <input type="date" value={hasta} onChange={(e) => filtrar(setHasta)(e.target.value)} className={CLASE_INPUT} />
          </Campo>
          <Campo etiqueta="Ruta">
            <select aria-label="Ruta" value={rutaId} onChange={(e) => filtrar(setRutaId)(e.target.value)} className={CLASE_INPUT}>
              <option value="">Todas</option>
              {rutas.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.codigo} · {r.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo etiqueta="Estado">
            <select aria-label="Estado" value={estado} onChange={(e) => filtrar(setEstado)(e.target.value as EstadoLiquidacion | '')} className={CLASE_INPUT}>
              <option value="">Todos</option>
              <option value="borrador">Borrador</option>
              <option value="cerrada">Cerrada</option>
              <option value="anulada">Anulada</option>
            </select>
          </Campo>
        </div>
      </Card>

      {listado.isLoading && <Cargando texto="Cargando liquidaciones…" />}
      {listado.isError && <AlertBanner>{mensajeError(listado.error)}</AlertBanner>}
      {listado.data && !listado.data.liquidaciones.length && <EmptyState titulo="Sin liquidaciones" detalle="No hay liquidaciones con esos filtros." />}
      {!!listado.data?.liquidaciones.length && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <caption className="sr-only">Liquidaciones</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-2 pr-3">Fecha</th>
                  <th className="pr-3">Ruta</th>
                  <th className="pr-3">Vendedor</th>
                  <th className="pr-3 text-right">Unidades</th>
                  <th className="pr-3 text-right">Venta</th>
                  <th className="pr-3 text-right">Dif. caja</th>
                  <th className="pr-3">Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {listado.data.liquidaciones.map((l) => (
                  <tr key={l.id} className="border-b border-line">
                    <td className="num py-2 pr-3">{fmtFecha(l.fecha)}</td>
                    <td className="pr-3">{l.ruta_nombre}</td>
                    <td className="pr-3">{l.vendedor_nombre}</td>
                    <td className="num pr-3 text-right">{fmtInt(l.unidades_vendidas)}</td>
                    <td className="num pr-3 text-right">{Q(l.venta_total)}</td>
                    <td className={`num pr-3 text-right ${Number(l.diferencia_caja) === 0 ? '' : 'font-semibold text-warn'}`}>{Q(l.diferencia_caja)}</td>
                    <td className="pr-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTILO_ESTADO[l.estado]}`}>
                        {l.estado}
                        {l.version > 1 && ` · v${l.version}`}
                      </span>
                    </td>
                    <td className="text-right">
                      <Button aria-label={`Ver detalle ${l.ruta_nombre} ${l.fecha}`} onClick={() => setDetalleId(l.id)}>
                        Detalle
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-muted">
            <span>
              Página {pagina + 1} de {paginas} · {fmtInt(total)} liquidaciones
            </span>
            <span className="flex gap-2">
              <Button disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </Button>
              <Button disabled={pagina + 1 >= paginas} onClick={() => setPagina((p) => p + 1)}>
                Siguiente
              </Button>
            </span>
          </div>
        </Card>
      )}

      {detalleId && <Detalle id={detalleId} onCerrar={() => setDetalleId(null)} />}
    </div>
  )
}

function Detalle({ id, onCerrar }: { id: string; onCerrar: () => void }) {
  const { data, isLoading, isError, error } = useLiquidacionDetalle(id)
  return (
    <Modal titulo="Detalle de la liquidación" onCerrar={onCerrar} acciones={<Button onClick={onCerrar}>Cerrar</Button>}>
      {isLoading && <Cargando />}
      {isError && <AlertBanner>{mensajeError(error)}</AlertBanner>}
      {data && (
        <div className="flex flex-col gap-3">
          <p>
            <strong>{data.ruta_nombre}</strong> · {data.vendedor_nombre} · {fmtFecha(data.fecha)} · {data.estado} (v{data.version})
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-muted">
                <th>SKU</th>
                <th className="text-right">Carg.</th>
                <th className="text-right">Vend.</th>
                <th className="text-right">Dev.</th>
                <th className="text-right">Merma</th>
                <th className="text-right">Monto</th>
              </tr>
            </thead>
            <tbody>
              {data.lineas.map((l) => (
                <tr key={l.producto_id} className="border-t border-line">
                  <td>
                    {l.sku}
                    {l.agotado && <span title="Se agotó: demanda censurada"> ⚠</span>}
                  </td>
                  <td className="num text-right">{fmt(l.cantidad_cargada)}</td>
                  <td className="num text-right">{fmt(l.cantidad_vendida)}</td>
                  <td className="num text-right">{fmt(l.cantidad_devuelta)}</td>
                  <td className="num text-right">{fmt(l.cantidad_merma)}</td>
                  <td className="num text-right">{Q(l.monto_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
            <dt className="text-muted">Venta total</dt>
            <dd className="num text-right">{Q(data.cuadre_dinero.venta_total)}</dd>
            <dt className="text-muted">Efectivo esperado</dt>
            <dd className="num text-right">{Q(data.cuadre_dinero.efectivo_esperado)}</dd>
            <dt className="text-muted">Efectivo entregado</dt>
            <dd className="num text-right">{Q(data.cuadre_dinero.efectivo_entregado)}</dd>
            <dt className="text-muted">Diferencia de caja</dt>
            <dd className={`num text-right font-semibold ${data.cuadre_dinero.supera_umbral ? 'text-bad' : ''}`}>{Q(data.cuadre_dinero.diferencia_caja)}</dd>
            <dt className="text-muted">Devolución esperada</dt>
            <dd className="num text-right">{fmt(data.devolucion_esperada)} u</dd>
          </dl>
          {data.anulado_motivo && <AlertBanner tipo="info">Anulada: {data.anulado_motivo}</AlertBanner>}
        </div>
      )}
    </Modal>
  )
}
