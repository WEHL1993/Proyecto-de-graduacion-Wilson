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
    <section className={`rounded-lg border border-line bg-panel p-4 ${className}`}>
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
  'rounded-md border border-line bg-panel px-2.5 py-1.5 text-sm text-ink disabled:opacity-50'
