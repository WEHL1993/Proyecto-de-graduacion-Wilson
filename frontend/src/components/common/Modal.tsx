import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

interface Props {
  titulo: string
  onCerrar: () => void
  children: ReactNode
  acciones: ReactNode
}

export function Modal({ titulo, onCerrar, children, acciones }: Props) {
  const tituloId = useId()
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previo = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const alTeclear = (e: KeyboardEvent) => e.key === 'Escape' && onCerrar()
    document.addEventListener('keydown', alTeclear)
    return () => {
      document.removeEventListener('keydown', alTeclear)
      previo?.focus()
    }
  }, [onCerrar])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onCerrar()}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={tituloId}
        tabIndex={-1}
        className="w-full max-w-md rounded-lg border border-line bg-panel p-5 shadow-xl"
      >
        <h2 id={tituloId} className="text-base font-semibold">
          {titulo}
        </h2>
        <div className="mt-3 text-sm text-ink">{children}</div>
        <div className="mt-5 flex justify-end gap-2">{acciones}</div>
      </div>
    </div>
  )
}
