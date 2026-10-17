import { useState } from 'react'
import type { InputHTMLAttributes, KeyboardEvent } from 'react'
import { Eye, EyeOff, Lock } from 'lucide-react'

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>

/** Campo de contraseña con candado, botón para mostrar/ocultar y aviso de Bloq Mayús. */
export function PasswordInput({ className = '', onKeyUp, ...rest }: Props) {
  const [visible, setVisible] = useState(false)
  const [mayusculas, setMayusculas] = useState(false)

  const alSoltar = (e: KeyboardEvent<HTMLInputElement>) => {
    setMayusculas(e.getModifierState('CapsLock'))
    onKeyUp?.(e)
  }

  return (
    <div>
      <div className="relative">
        <Lock aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <input
          {...rest}
          type={visible ? 'text' : 'password'}
          onKeyUp={alSoltar}
          className={`w-full rounded-lg border border-line bg-white py-2.5 pl-10 pr-11 text-sm text-ink placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 ${className}`}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
          aria-pressed={visible}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted hover:bg-surface hover:text-ink"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {mayusculas && <p className="mt-1 text-xs text-warn">Bloq Mayús está activado.</p>}
    </div>
  )
}
