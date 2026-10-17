import type { ReactNode } from 'react'

export function Card({
  titulo,
  acciones,
  children,
  className = '',
}: {
  titulo?: string
  acciones?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-xl border border-line bg-panel p-5 shadow-sm ${className}`}>
      {(titulo || acciones) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {titulo && <h2 className="text-sm font-semibold">{titulo}</h2>}
          {acciones}
        </header>
      )}
      {children}
    </section>
  )
}

export function Campo({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-muted">
      {etiqueta}
      {children}
    </label>
  )
}

export const CLASE_INPUT =
  'rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:opacity-50'
