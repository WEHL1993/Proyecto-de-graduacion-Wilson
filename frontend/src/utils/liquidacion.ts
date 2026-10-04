// Cálculos y validaciones de la pantalla de liquidación (ADR-14). Puros y sin React: la
// autoridad sigue siendo el servidor, esto da cuadres en vivo y evita envíos inválidos.
import type { LiquidacionRequest, LiquidacionResponse, LineaPrecarga } from '../types'

export interface FilaForm {
  producto_id: string
  sku: string
  nombre: string
  cargada: string
  vendida: string
  devuelta: string
  merma: string
  precio: string
  agotado: boolean
  justificacion: string
  /** Lo despachado según la carga (para pedir justificación si se edita); `null` sin carga. */
  despachada: number | null
}

export interface PagosForm {
  efectivo: string
  transferencia: string
  credito: string
  cobro_saldos: string
  gastos: string
  efectivo_entregado: string
}

export const PAGOS_VACIOS: PagosForm = {
  efectivo: '',
  transferencia: '',
  credito: '',
  cobro_saldos: '',
  gastos: '',
  efectivo_entregado: '',
}

const redondear = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100

/** Número del campo; vacío = 0 y texto inválido = NaN. */
export const num = (v: string): number => (v.trim() === '' ? 0 : Number(v.replace(',', '.')))
export const esMontoValido = (v: string): boolean => {
  const n = num(v)
  return Number.isFinite(n) && n >= 0
}

export const diferenciaFila = (f: FilaForm): number =>
  redondear(num(f.cargada) - num(f.vendida) - num(f.devuelta) - num(f.merma))
export const montoFila = (f: FilaForm): number => redondear(num(f.vendida) * num(f.precio))

export type EstadoFila = 'cuadra' | 'falta' | 'excede'
export function estadoFila(f: FilaForm): EstadoFila {
  const d = diferenciaFila(f)
  return d === 0 ? 'cuadra' : d > 0 ? 'falta' : 'excede'
}

export function totalesUnidades(filas: FilaForm[]) {
  const suma = (k: 'cargada' | 'vendida' | 'devuelta' | 'merma') =>
    redondear(filas.reduce((a, f) => a + (Number.isFinite(num(f[k])) ? num(f[k]) : 0), 0))
  return {
    cargadas: suma('cargada'),
    vendidas: suma('vendida'),
    devueltas: suma('devuelta'),
    merma: suma('merma'),
  }
}

export const ventaTotal = (filas: FilaForm[]): number =>
  redondear(filas.reduce((a, f) => a + (Number.isFinite(montoFila(f)) ? montoFila(f) : 0), 0))

export const totalPagos = (p: PagosForm): number =>
  redondear(num(p.efectivo) + num(p.transferencia) + num(p.credito))

/** efectivo esperado = efectivo + cobro de saldos anteriores − gastos de ruta. */
export const efectivoEsperado = (p: PagosForm): number =>
  redondear(num(p.efectivo) + num(p.cobro_saldos) - num(p.gastos))

/** diferencia = entregado − esperado (negativa = faltante). */
export const diferenciaCaja = (p: PagosForm): number =>
  redondear(num(p.efectivo_entregado) - efectivoEsperado(p))

export type SemaforoCaja = 'verde' | 'ambar' | 'rojo'
/** Verde = cuadra; ámbar = diferencia dentro del umbral; rojo = sobre el umbral (alerta). */
export function semaforoCaja(diferencia: number, umbral: number): SemaforoCaja {
  const d = Math.abs(diferencia)
  if (d === 0) return 'verde'
  return d <= umbral ? 'ambar' : 'rojo'
}

export interface Validacion {
  /** Impiden guardar el borrador. */
  errores: string[]
  /** Impiden cerrar (unidades o dinero sin cuadrar). */
  pendientes: string[]
}

export function validar(filas: FilaForm[], pagos: PagosForm): Validacion {
  const errores: string[] = []
  const pendientes: string[] = []
  for (const f of filas) {
    for (const [k, v] of [['cargada', f.cargada], ['vendida', f.vendida], ['devuelta', f.devuelta], ['merma', f.merma], ['precio', f.precio]] as const) {
      if (!esMontoValido(v)) errores.push(`${f.sku}: «${k}» debe ser un número mayor o igual a 0.`)
    }
    if (estadoFila(f) === 'excede') errores.push(`${f.sku}: vendido + devuelto + merma excede lo cargado.`)
    if (estadoFila(f) === 'falta') pendientes.push(`${f.sku}: faltan ${diferenciaFila(f)} unidades por justificar.`)
    if (f.despachada !== null && num(f.cargada) !== f.despachada && !f.justificacion.trim()) {
      errores.push(`${f.sku}: lo cargado difiere de lo despachado (${f.despachada}); indique la justificación.`)
    }
  }
  for (const [k, v] of Object.entries(pagos)) {
    if (!esMontoValido(v)) errores.push(`«${k.replace('_', ' ')}» debe ser un monto mayor o igual a 0.`)
  }
  if (!filas.some((f) => num(f.vendida) > 0 || num(f.cargada) > 0)) {
    errores.push('Ingrese al menos una presentación con unidades cargadas o vendidas.')
  }
  if (ventaTotal(filas) !== totalPagos(pagos)) {
    pendientes.push('La venta total debe igualar efectivo + transferencia + crédito.')
  }
  return { errores, pendientes }
}

const aTexto = (n: number | string) => String(n)

export function aSolicitud(
  fecha: string,
  rutaId: string,
  filas: FilaForm[],
  pagos: PagosForm,
  observaciones: string,
): LiquidacionRequest {
  const dec = (v: string) => aTexto(num(v))
  return {
    fecha,
    ruta_id: rutaId,
    lineas: filas
      .filter((f) => num(f.cargada) > 0 || num(f.vendida) > 0 || num(f.devuelta) > 0 || num(f.merma) > 0)
      .map((f) => ({
        producto_id: f.producto_id,
        cantidad_cargada: dec(f.cargada),
        cantidad_vendida: dec(f.vendida),
        cantidad_devuelta: dec(f.devuelta),
        cantidad_merma: dec(f.merma),
        precio_unitario: dec(f.precio),
        agotado: f.agotado,
        justificacion_carga: f.justificacion.trim() || null,
      })),
    pagos: {
      efectivo: dec(pagos.efectivo),
      transferencia: dec(pagos.transferencia),
      credito: dec(pagos.credito),
      cobro_saldos: dec(pagos.cobro_saldos),
      gastos: dec(pagos.gastos),
      efectivo_entregado: dec(pagos.efectivo_entregado),
    },
    observaciones: observaciones.trim() || null,
  }
}

const sinCeros = (v: string | number): string => (Number(v) === 0 ? '' : String(Number(v)))

export function filasDePrecarga(lineas: LineaPrecarga[], conCarga: boolean): FilaForm[] {
  return lineas.map((l) => ({
    producto_id: l.producto_id,
    sku: l.sku,
    nombre: l.producto_nombre,
    cargada: sinCeros(l.cantidad_cargada),
    vendida: '',
    devuelta: '',
    merma: '',
    precio: String(Number(l.precio_unitario)),
    agotado: false,
    justificacion: '',
    despachada: conCarga ? Number(l.cantidad_cargada) : null,
  }))
}

export function filasDeLiquidacion(l: LiquidacionResponse, despachado: Map<string, number> | null): FilaForm[] {
  return l.lineas.map((x) => ({
    producto_id: x.producto_id,
    sku: x.sku,
    nombre: x.producto_nombre,
    cargada: sinCeros(x.cantidad_cargada),
    vendida: sinCeros(x.cantidad_vendida),
    devuelta: sinCeros(x.cantidad_devuelta),
    merma: sinCeros(x.cantidad_merma),
    precio: String(Number(x.precio_unitario)),
    agotado: x.agotado,
    justificacion: x.justificacion_carga ?? '',
    despachada: despachado ? (despachado.get(x.producto_id) ?? 0) : null,
  }))
}

export function pagosDeLiquidacion(l: LiquidacionResponse): PagosForm {
  const p = l.pagos
  return {
    efectivo: sinCeros(p.efectivo ?? 0),
    transferencia: sinCeros(p.transferencia ?? 0),
    credito: sinCeros(p.credito ?? 0),
    cobro_saldos: sinCeros(p.cobro_saldos ?? 0),
    gastos: sinCeros(p.gastos ?? 0),
    efectivo_entregado: sinCeros(p.efectivo_entregado ?? 0),
  }
}
