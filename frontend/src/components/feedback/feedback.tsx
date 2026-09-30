import type { ReactNode } from 'react'

export function AlertBanner({
  tipo = 'error',
  children,
}: {
  tipo?: 'error' | 'info' | 'exito'
  children: ReactNode
}) {
  const color = { error: 'border-bad text-bad', info: 'border-brand text-brand', exito: 'border-good text-good' }[tipo]
  const icono = { error: '⛔', info: 'ℹ', exito: '✔' }[tipo]
  return (
    <div role={tipo === 'error' ? 'alert' : 'status'} className={`rounded-md border ${color} bg-panel px-3 py-2 text-sm`}>
      <span aria-hidden className="mr-2">
        {icono}
      </span>
      <span className="text-ink">{children}</span>
    </div>
  )
}

export function EmptyState({ titulo, detalle, children }: { titulo: string; detalle?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <p className="font-medium">{titulo}</p>
      {detalle && <p className="max-w-md text-sm text-muted">{detalle}</p>}
      {children}
    </div>
  )
}

export function Cargando({ texto = 'Cargando…' }: { texto?: string }) {
  return (
    <p role="status" className="py-6 text-center text-sm text-muted">
      {texto}
    </p>
  )
}
