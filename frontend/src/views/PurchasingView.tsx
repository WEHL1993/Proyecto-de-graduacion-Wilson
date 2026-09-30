import { useMemo, useState } from 'react'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { usePedidoActions, usePedidos, useSugerencias } from '../hooks/usePurchasing'
import { usePermissions } from '../hooks/usePermissions'
import type { EstadoPedido, PedidoOut, SugerenciaCompra } from '../types'
import { fmt, fmtFecha, hoyISO, sumarDias } from '../utils/format'
import { mensajeError } from '../utils/errors'

const HORIZONTES = [7, 14, 30]
const ETAPAS: EstadoPedido[] = ['borrador', 'enviado', 'confirmado', 'recibido']
const ESTADOS_FILTRO: (EstadoPedido | '')[] = ['', 'borrador', 'enviado', 'confirmado', 'recibido', 'cancelado']

export interface GrupoProveedor {
  proveedorId: string
  nombre: string
  leadTimeDias: number
  filas: SugerenciaCompra[]
}

/** Agrupa las sugerencias por proveedor (cada orden de compra es de un solo proveedor). */
export function agruparPorProveedor(sugerencias: SugerenciaCompra[]): GrupoProveedor[] {
  const grupos = new Map<string, GrupoProveedor>()
  for (const s of sugerencias) {
    const g = grupos.get(s.proveedor_id) ?? {
      proveedorId: s.proveedor_id,
      nombre: s.proveedor_nombre,
      leadTimeDias: s.lead_time_dias,
      filas: [],
    }
    g.filas.push(s)
    grupos.set(s.proveedor_id, g)
  }
  return [...grupos.values()]
}

/** Cantidad de una línea de orden: número > 0 con hasta 2 decimales. */
export const cantidadValida = (texto: string): boolean => /^\d+(\.\d{1,2})?$/.test(texto) && Number(texto) > 0

/** Wireframe Módulo 6 — Abastecimiento: sugerencias de reabastecimiento y seguimiento de órdenes. */
export function PurchasingView() {
  const { can } = usePermissions()
  const puedeGestionar = can('pedido_proveedor:gestionar')
  const [horizonte, setHorizonte] = useState(7)
  const [aviso, setAviso] = useState<string | null>(null)

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Abastecimiento y Pedidos</h1>
      {aviso && <AlertBanner tipo="exito">{aviso}</AlertBanner>}
      {puedeGestionar && (
        <Sugerencias horizonte={horizonte} onHorizonte={setHorizonte} onCreado={setAviso} />
      )}
      <Pedidos />
    </div>
  )
}

// ------------------------------------------------------------------ sugerencias
function Sugerencias({
  horizonte,
  onHorizonte,
  onCreado,
}: {
  horizonte: number
  onHorizonte: (d: number) => void
  onCreado: (msg: string) => void
}) {
  const sugerencias = useSugerencias(horizonte, true)
  const grupos = useMemo(() => agruparPorProveedor(sugerencias.data?.sugerencias ?? []), [sugerencias.data])

  return (
    <Card
      titulo="Sugerencias de reabastecimiento"
      acciones={
        <Campo etiqueta="Horizonte de demanda">
          <select
            className={CLASE_INPUT}
            value={horizonte}
            onChange={(e) => onHorizonte(Number(e.target.value))}
          >
            {HORIZONTES.map((d) => (
              <option key={d} value={d}>
                Próximos {d} días
              </option>
            ))}
          </select>
        </Campo>
      }
    >
      <p className="mb-3 text-xs text-muted">
        Cantidad a pedir = máx(0, (demanda proyectada + stock mínimo) − stock actual).
      </p>
      {sugerencias.isPending && <Cargando texto="Calculando sugerencias…" />}
      {sugerencias.isError && <AlertBanner>{mensajeError(sugerencias.error)}</AlertBanner>}
      {sugerencias.data?.advertencias.map((a) => (
        <div key={a} className="mb-2">
          <AlertBanner tipo="info">{a}</AlertBanner>
        </div>
      ))}
      {sugerencias.data && grupos.length === 0 && (
        <EmptyState
          titulo="Sin necesidades de reabastecimiento"
          detalle="El stock actual cubre la demanda proyectada y el punto de reorden de todos los productos."
        />
      )}
      <div className="space-y-4">
        {grupos.map((g) => (
          <GrupoOrden key={`${g.proveedorId}-${horizonte}`} grupo={g} onCreado={onCreado} />
        ))}
      </div>
    </Card>
  )
}

function GrupoOrden({ grupo, onCreado }: { grupo: GrupoProveedor; onCreado: (msg: string) => void }) {
  const { crear } = usePedidoActions()
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set(grupo.filas.map((f) => f.producto_id)))
  const [cantidades, setCantidades] = useState<Record<string, string>>(
    Object.fromEntries(grupo.filas.map((f) => [f.producto_id, String(f.cantidad_sugerida)])),
  )
  const [fechaEsperada, setFechaEsperada] = useState(sumarDias(hoyISO(), grupo.leadTimeDias))

  const elegidas = grupo.filas.filter((f) => seleccion.has(f.producto_id))
  const invalidas = elegidas.some((f) => !cantidadValida(cantidades[f.producto_id] ?? ''))
  const total = elegidas.reduce(
    (t, f) => t + (cantidadValida(cantidades[f.producto_id]) ? Number(cantidades[f.producto_id]) * Number(f.costo_unitario) : 0),
    0,
  )

  const generar = (enviar: boolean) =>
    crear.mutate(
      {
        proveedor_id: grupo.proveedorId,
        fecha_esperada: fechaEsperada || null,
        enviar,
        items: elegidas.map((f) => ({ producto_id: f.producto_id, cantidad: cantidades[f.producto_id] })),
      },
      {
        onSuccess: (p) =>
          onCreado(`Orden a ${p.proveedor_nombre} creada en estado «${p.estado}» por ${fmt(p.total)}.`),
      },
    )

  const alternar = (id: string) =>
    setSeleccion((prev) => {
      const sig = new Set(prev)
      if (!sig.delete(id)) sig.add(id)
      return sig
    })

  return (
    <section aria-label={`Sugerencias de ${grupo.nombre}`} className="rounded-md border border-line">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-3 py-2">
        <h3 className="text-sm font-semibold">{grupo.nombre}</h3>
        <span className="text-xs text-muted">Lead time: {grupo.leadTimeDias} d</span>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="w-8 px-3 py-2" />
              <th className="py-2">Producto</th>
              <th className="py-2 text-right">Stock actual</th>
              <th className="py-2 text-right">Mínimo</th>
              <th className="py-2 text-right">Demanda proy.</th>
              <th className="py-2 text-right">Sugerida</th>
              <th className="px-3 py-2 text-right">A pedir</th>
            </tr>
          </thead>
          <tbody>
            {grupo.filas.map((f) => {
              const valor = cantidades[f.producto_id] ?? ''
              const error = seleccion.has(f.producto_id) && !cantidadValida(valor)
              return (
                <tr key={f.producto_id} className="border-b border-line last:border-0">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Incluir ${f.sku}`}
                      checked={seleccion.has(f.producto_id)}
                      onChange={() => alternar(f.producto_id)}
                    />
                  </td>
                  <td className="py-2">
                    {f.nombre} <span className="font-mono text-xs text-muted">{f.sku}</span>
                    {!f.pronostico_disponible && (
                      <span className="ml-2 text-xs text-warn" title="Sin pronóstico: solo punto de reorden">
                        sin pronóstico
                      </span>
                    )}
                  </td>
                  <td className="num py-2 text-right">{fmt(f.stock_actual)}</td>
                  <td className="num py-2 text-right">{fmt(f.stock_minimo)}</td>
                  <td className="num py-2 text-right">{fmt(f.demanda_proyectada)}</td>
                  <td className="num py-2 text-right font-medium">{fmt(f.cantidad_sugerida)}</td>
                  <td className="px-3 py-2 text-right">
                    <input
                      inputMode="decimal"
                      aria-label={`Cantidad ${f.sku}`}
                      aria-invalid={error}
                      disabled={!seleccion.has(f.producto_id)}
                      value={valor}
                      onChange={(e) => setCantidades((c) => ({ ...c, [f.producto_id]: e.target.value }))}
                      className={`${CLASE_INPUT} num w-24 text-right ${error ? 'border-bad' : ''}`}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <footer className="flex flex-wrap items-end justify-between gap-3 px-3 py-3">
        <Campo etiqueta="Fecha esperada de entrega">
          <input
            type="date"
            min={hoyISO()}
            className={CLASE_INPUT}
            value={fechaEsperada}
            onChange={(e) => setFechaEsperada(e.target.value)}
          />
        </Campo>
        <div className="flex flex-wrap items-center gap-3">
          <span className="num text-sm">
            Total estimado: <strong>{fmt(total)}</strong>
          </span>
          <Button disabled={!elegidas.length || invalidas || crear.isPending} onClick={() => generar(false)}>
            Guardar borrador
          </Button>
          <Button
            variant="primary"
            disabled={!elegidas.length || invalidas || crear.isPending}
            onClick={() => generar(true)}
          >
            Aprobar y enviar
          </Button>
        </div>
        {crear.isError && (
          <div className="w-full">
            <AlertBanner>{mensajeError(crear.error)}</AlertBanner>
          </div>
        )}
      </footer>
    </section>
  )
}

// ------------------------------------------------------------------ seguimiento
function Pedidos() {
  const [estado, setEstado] = useState<EstadoPedido | ''>('')
  const pedidos = usePedidos(estado || undefined)

  return (
    <Card
      titulo="Seguimiento de órdenes"
      acciones={
        <select
          aria-label="Filtrar por estado"
          className={CLASE_INPUT}
          value={estado}
          onChange={(e) => setEstado(e.target.value as EstadoPedido | '')}
        >
          {ESTADOS_FILTRO.map((s) => (
            <option key={s} value={s}>
              {s || 'Todos los estados'}
            </option>
          ))}
        </select>
      }
    >
      {pedidos.isPending && <Cargando texto="Cargando órdenes…" />}
      {pedidos.isError && <AlertBanner>{mensajeError(pedidos.error)}</AlertBanner>}
      {pedidos.data && pedidos.data.items.length === 0 && (
        <EmptyState titulo="Sin órdenes" detalle="Aún no hay órdenes de compra con este filtro." />
      )}
      <ul className="space-y-3">
        {pedidos.data?.items.map((p) => (
          <FilaPedido key={p.id} pedido={p} />
        ))}
      </ul>
    </Card>
  )
}

export function Progreso({ estado }: { estado: EstadoPedido }) {
  if (estado === 'cancelado') return <span className="text-xs font-semibold text-bad">Cancelado</span>
  const actual = ETAPAS.indexOf(estado)
  return (
    <ol aria-label={`Estado: ${estado}`} className="flex flex-wrap items-center gap-1 text-xs">
      {ETAPAS.map((e, i) => (
        <li
          key={e}
          aria-current={i === actual ? 'step' : undefined}
          className={`rounded-full border px-2.5 py-0.5 ${
            i === actual
              ? 'border-brand bg-brand/10 font-semibold text-brand'
              : i < actual
                ? 'border-good text-good'
                : 'border-line text-muted'
          }`}
        >
          {i < actual && <span aria-hidden>✔ </span>}
          {e}
        </li>
      ))}
    </ol>
  )
}

function FilaPedido({ pedido: p }: { pedido: PedidoOut }) {
  const { can } = usePermissions()
  const acciones = usePedidoActions()
  const [fecha, setFecha] = useState(p.fecha_esperada ?? sumarDias(hoyISO(), 1))
  const [abierto, setAbierto] = useState(false)
  const error = [acciones.enviar, acciones.cancelar, acciones.confirmar, acciones.recibir].find((m) => m.isError)
  const ocupado = [acciones.enviar, acciones.cancelar, acciones.confirmar, acciones.recibir].some((m) => m.isPending)

  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">
            {p.proveedor_nombre} <span className="font-mono text-xs font-normal text-muted">{p.id.slice(0, 8)}</span>
          </p>
          <p className="num text-xs text-muted">
            Pedido {fmtFecha(p.fecha_pedido)} · Entrega {fmtFecha(p.fecha_esperada)} · Total {fmt(p.total)}
          </p>
        </div>
        <Progreso estado={p.estado} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button className="px-2.5 py-1 text-xs" onClick={() => setAbierto((v) => !v)} aria-expanded={abierto}>
          {abierto ? 'Ocultar detalle' : `Ver detalle (${p.items.length})`}
        </Button>
        {can('pedido_proveedor:gestionar') && p.estado === 'borrador' && (
          <Button variant="primary" disabled={ocupado} onClick={() => acciones.enviar.mutate(p.id)}>
            Aprobar y enviar
          </Button>
        )}
        {can('pedido_proveedor:gestionar') && (p.estado === 'borrador' || p.estado === 'enviado') && (
          <Button variant="danger" disabled={ocupado} onClick={() => acciones.cancelar.mutate(p.id)}>
            Cancelar
          </Button>
        )}
        {can('pedido_proveedor:confirmar') && p.estado === 'enviado' && (
          <>
            <input
              type="date"
              aria-label="Fecha estimada de entrega"
              min={p.fecha_pedido}
              className={CLASE_INPUT}
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
            <Button
              variant="primary"
              disabled={ocupado || !fecha}
              onClick={() => acciones.confirmar.mutate({ id: p.id, fecha })}
            >
              Confirmar pedido
            </Button>
          </>
        )}
        {can('inventario:ajustar') && p.estado === 'confirmado' && (
          <Button variant="primary" disabled={ocupado} onClick={() => acciones.recibir.mutate(p.id)}>
            Registrar recepción física
          </Button>
        )}
      </div>

      {error && (
        <div className="mt-2">
          <AlertBanner>{mensajeError(error.error)}</AlertBanner>
        </div>
      )}

      {abierto && (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-1.5">Producto</th>
              <th className="py-1.5 text-right">Cantidad</th>
              <th className="py-1.5 text-right">Costo unit.</th>
              <th className="py-1.5 text-right">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {p.items.map((i) => (
              <tr key={i.producto_id} className="border-b border-line last:border-0">
                <td className="py-1.5">
                  {i.producto_nombre} <span className="font-mono text-xs text-muted">{i.sku}</span>
                </td>
                <td className="num py-1.5 text-right">{fmt(i.cantidad)}</td>
                <td className="num py-1.5 text-right">{fmt(i.costo_unitario)}</td>
                <td className="num py-1.5 text-right">{fmt(i.subtotal)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </li>
  )
}
