import type { ButtonHTMLAttributes } from 'react'

type Variante = 'primary' | 'secondary' | 'danger'

const ESTILOS: Record<Variante, string> = {
  primary: 'bg-navy text-white shadow-sm hover:bg-brand',
  secondary: 'border border-line bg-white text-ink shadow-sm hover:bg-surface',
  danger: 'border border-bad text-bad hover:bg-bad/10',
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variante
}

export function Button({ variant = 'secondary', className = '', type = 'button', ...rest }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${ESTILOS[variant]} ${className}`}
      {...rest}
    />
  )
}
