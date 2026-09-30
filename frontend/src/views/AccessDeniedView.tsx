import { Link } from 'react-router-dom'

export function AccessDeniedView() {
  return (
    <div role="alert" className="mx-auto mt-16 max-w-md rounded-lg border border-line bg-panel p-6 text-center">
      <p className="text-3xl" aria-hidden>
        ⛔
      </p>
      <h1 className="mt-2 text-lg font-semibold">Acceso denegado</h1>
      <p className="mt-1 text-sm text-muted">Su rol no tiene permiso para ver esta sección.</p>
      <Link to="/" className="mt-4 inline-block text-sm text-brand underline">
        Volver al inicio
      </Link>
    </div>
  )
}
