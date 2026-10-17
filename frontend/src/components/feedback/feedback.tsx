import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { CheckCircle2, Info, XCircle } from 'lucide-react'
import { useToastApi } from './toast'

/**
 * Mensaje de retroalimentación. Con `ToastProvider` se muestra como notificación flotante (toast)
 * y no ocupa espacio en la página; con `fijo` (o sin proveedor, p. ej. en tests) se dibuja en línea.
 */
export function AlertBanner({
  tipo = 'error',
  fijo = false,
  children,
}: {
  tipo?: 'error' | 'info' | 'exito'
  fijo?: boolean
  children: ReactNode
}) {
  const toasts = useToastApi()
  const clave = typeof children === 'string' ? children : null

  useEffect(() => {
    if (!toasts || fijo) return
    const id = toasts.push(tipo, children)
    return () => toasts.remove(id)
    // Se emite al montar (o si cambia el texto); no debe reemitirse en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toasts, fijo, tipo, clave])

  if (toasts && !fijo) return null
  const color = { error: 'border-bad text-bad', info: 'border-brand text-brand', exito: 'border-good text-good' }[tipo]
  const Icono = { error: XCircle, info: Info, exito: CheckCircle2 }[tipo]
  return (
    <div role={tipo === 'error' ? 'alert' : 'status'} className={`flex items-start gap-2 rounded-lg border ${color} bg-panel px-3 py-2.5 text-sm`}>
      <Icono aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
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
