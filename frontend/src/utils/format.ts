const num = new Intl.NumberFormat('es-GT', { maximumFractionDigits: 2 })
const int = new Intl.NumberFormat('es-GT', { maximumFractionDigits: 0 })

export const fmt = (v: number | string | null | undefined, unidad = ''): string =>
  v === null || v === undefined || v === '' ? 's/d' : `${num.format(Number(v))}${unidad}`
export const fmtInt = (v: number | string): string => int.format(Number(v))
export const fmtFecha = (iso: string | null | undefined): string => (iso ? iso.slice(0, 10) : '—')

export const hoyISO = (): string => new Date().toISOString().slice(0, 10)
export function sumarDias(iso: string, dias: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + dias)
  return d.toISOString().slice(0, 10)
}

export type Semaforo = 'verde' | 'amarillo' | 'rojo' | 'sin_dato'
/** 🟢 MAPE ≤ umbral·0.8, 🟡 ≤ umbral, 🔴 > umbral (wireframe 2b). */
export function semaforoMape(mape: number | null | undefined, umbral: number): Semaforo {
  if (mape === null || mape === undefined) return 'sin_dato'
  if (mape <= umbral * 0.8) return 'verde'
  if (mape <= umbral) return 'amarillo'
  return 'rojo'
}
