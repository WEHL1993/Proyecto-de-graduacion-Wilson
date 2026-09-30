import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../app/providers/AuthProvider'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo } from '../components/common/Card'
import { AlertBanner } from '../components/feedback/feedback'
import { apiError, mensajeError } from '../utils/errors'

export function LoginView() {
  const { usuario, login, sesionExpirada } = useAuth()
  const navegar = useNavigate()
  const ubicacion = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  if (usuario) return <Navigate to="/" replace />

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await login(email.trim(), password)
      const destino = (ubicacion.state as { desde?: string } | null)?.desde ?? '/'
      navegar(destino, { replace: true })
    } catch (err) {
      setError(apiError(err)?.mensaje ?? mensajeError(err))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={enviar} className="w-full max-w-sm space-y-4 rounded-lg border border-line bg-panel p-6">
        <div>
          <h1 className="text-lg font-bold">DS Predictive</h1>
          <p className="text-sm text-muted">Análisis predictivo de demanda</p>
        </div>
        {sesionExpirada && <AlertBanner tipo="info">Su sesión expiró. Inicie sesión de nuevo.</AlertBanner>}
        {error && <AlertBanner>{error}</AlertBanner>}
        <Campo etiqueta="Correo">
          <input
            type="email"
            required
            autoComplete="username"
            className={CLASE_INPUT}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Campo>
        <Campo etiqueta="Contraseña">
          <input
            type="password"
            required
            minLength={8}
            autoComplete="current-password"
            className={CLASE_INPUT}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Campo>
        <Button type="submit" variant="primary" disabled={enviando} className="w-full justify-center">
          {enviando ? 'Ingresando…' : 'Ingresar'}
        </Button>
      </form>
    </main>
  )
}
