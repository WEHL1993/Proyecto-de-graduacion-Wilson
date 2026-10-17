import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'

export type TipoToast = 'error' | 'exito' | 'info' | 'aviso'

interface ToastItem {
  id: number
  tipo: TipoToast
  contenido: ReactNode
  duracion: number
}

interface ToastApi {
  push: (tipo: TipoToast, contenido: ReactNode, duracion?: number) => number
  remove: (id: number) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const ESTILO: Record<TipoToast, { titulo: string; icono: typeof Info; anillo: string; barra: string }> = {
  exito: { titulo: 'Operación exitosa', icono: CheckCircle2, anillo: 'bg-good/10 text-good', barra: 'bg-good' },
  error: { titulo: 'Ocurrió un error', icono: XCircle, anillo: 'bg-bad/10 text-bad', barra: 'bg-bad' },
  aviso: { titulo: 'Atención', icono: AlertTriangle, anillo: 'bg-warn/10 text-warn', barra: 'bg-warn' },
  info: { titulo: 'Información', icono: Info, anillo: 'bg-brand/10 text-brand', barra: 'bg-brand' },
}

const DURACION: Record<TipoToast, number> = { exito: 4000, info: 5000, aviso: 6000, error: 7000 }

/** Contexto opcional: sin proveedor (p. ej. en tests) devuelve `null` y quien lo usa debe degradar. */
export function useToastApi() {
  return useContext(ToastContext)
}

/** Notificaciones imperativas: `const toast = useToast(); toast.exito('Guardado')`. */
export function useToast() {
  const api = useContext(ToastContext)
  return useMemo(
    () => ({
      exito: (m: ReactNode) => api?.push('exito', m),
      error: (m: ReactNode) => api?.push('error', m),
      aviso: (m: ReactNode) => api?.push('aviso', m),
      info: (m: ReactNode) => api?.push('info', m),
    }),
    [api],
  )
}

function Toast({ item, alCerrar }: { item: ToastItem; alCerrar: () => void }) {
  const { titulo, icono: Icono, anillo, barra } = ESTILO[item.tipo]
  const restante = useRef(item.duracion)
  const inicio = useRef(0)
  const [pausado, setPausado] = useState(false)

  // El temporizador se detiene al pasar el cursor y retoma con el tiempo que faltaba.
  useEffect(() => {
    if (pausado) return
    inicio.current = Date.now()
    const t = window.setTimeout(alCerrar, restante.current)
    return () => {
      window.clearTimeout(t)
      restante.current -= Date.now() - inicio.current
    }
  }, [pausado, alCerrar])

  return (
    <div
      role={item.tipo === 'error' ? 'alert' : 'status'}
      onMouseEnter={() => setPausado(true)}
      onMouseLeave={() => setPausado(false)}
      className="pointer-events-auto relative w-full animate-toast-in overflow-hidden rounded-xl border border-line bg-panel shadow-[0_10px_30px_rgba(15,37,87,0.18)]"
    >
      <div className="flex items-start gap-3 p-4 pr-10">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${anillo}`}>
          <Icono aria-hidden className="h-5 w-5" />
        </span>
        <div className="min-w-0 text-sm">
          <p className="font-semibold text-ink">{titulo}</p>
          <div className="mt-0.5 break-words text-muted">{item.contenido}</div>
        </div>
      </div>
      <button
        type="button"
        onClick={alCerrar}
        aria-label="Cerrar notificación"
        className="absolute right-2 top-2 rounded-md p-1 text-muted hover:bg-surface hover:text-ink"
      >
        <X className="h-4 w-4" />
      </button>
      <div
        aria-hidden
        className={`absolute bottom-0 left-0 h-1 w-full origin-left animate-toast-barra ${barra}`}
        style={{ animationDuration: `${item.duracion}ms`, animationPlayState: pausado ? 'paused' : 'running' }}
      />
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const contador = useRef(0)

  const remove = useCallback((id: number) => setItems((v) => v.filter((t) => t.id !== id)), [])
  const push = useCallback((tipo: TipoToast, contenido: ReactNode, duracion = DURACION[tipo]) => {
    const id = ++contador.current
    setItems((v) => [...v.slice(-3), { id, tipo, contenido, duracion }])
    return id
  }, [])
  const api = useMemo(() => ({ push, remove }), [push, remove])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 top-4 z-50 flex w-[calc(100%-2rem)] max-w-sm flex-col gap-3"
      >
        {items.map((t) => (
          <Toast key={t.id} item={t} alCerrar={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
