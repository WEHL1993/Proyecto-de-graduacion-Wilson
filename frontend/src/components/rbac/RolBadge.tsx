// `roles.color` guarda un token semántico; aquí se traduce a los estilos de la interfaz.
const ESTILO_COLOR: Record<string, string> = {
  bad: 'bg-bad/10 text-bad',
  brand: 'bg-brand/10 text-brand',
  good: 'bg-good/10 text-good',
  warn: 'bg-warn/10 text-warn',
  neutral: 'bg-surface text-muted',
}

export function RolBadge({ rol, color = 'neutral', inactivo = false }: { rol: string; color?: string; inactivo?: boolean }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${ESTILO_COLOR[color] ?? ESTILO_COLOR.neutral} ${inactivo ? 'line-through opacity-60' : ''}`}
    >
      {rol}
    </span>
  )
}
