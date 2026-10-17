import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../app/providers/AuthProvider'
import { BarChart3, Boxes, Loader2, LogIn, Mail, Receipt } from 'lucide-react'
import { PasswordInput } from '../components/common/PasswordInput'
import { AlertBanner } from '../components/feedback/feedback'
import { apiError, mensajeError } from '../utils/errors'
import logoBigCola from '../assets/big-cola-logo.svg'

export function LoginView() {
  const { usuario, login, sesionExpirada } = useAuth()
  const ubicacion = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  // Tras iniciar sesión: la pantalla que se intentaba abrir o la de inicio configurada para el rol.
  const desde = (ubicacion.state as { desde?: string } | null)?.desde
  if (usuario) return <Navigate to={desde ?? usuario.pantalla_inicio ?? '/'} replace />

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await login(email.trim(), password)
    } catch (err) {
      setError(apiError(err)?.mensaje ?? mensajeError(err))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-navy via-[#14307a] to-brand p-12 text-white lg:flex">
        <div className="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-white/5" aria-hidden />
        <div className="absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-white/5" aria-hidden />
        <div className="relative space-y-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15">
              <BarChart3 className="h-5 w-5" aria-hidden />
            </span>
            <span className="text-lg font-semibold tracking-tight">DS Predictive</span>
          </div>
          <img src={logoBigCola} alt="Big Cola" className="mx-auto h-52 w-auto" />
        </div>
        <div className="relative max-w-md space-y-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-blue-200">Sistema de</p>
            <h2 className="mt-2 text-3xl font-bold leading-tight">
              Análisis Predictivo basado en Machine Learning
            </h2>
            <p className="mt-3 text-blue-100">
              Predicción de demanda, control de inventario y liquidación diaria en un solo lugar.
            </p>
          </div>
          <ul className="space-y-4 text-sm">
            {[
              [BarChart3, 'Predicción de demanda por producto y ruta'],
              [Boxes, 'Inventario y kardex en tiempo real'],
              [Receipt, 'Liquidación diaria de ventas y cajas'],
            ].map(([Icono, texto]) => {
              const I = Icono as typeof BarChart3
              return (
                <li key={texto as string} className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                    <I className="h-4 w-4" aria-hidden />
                  </span>
                  {texto as string}
                </li>
              )
            })}
          </ul>
        </div>
        <p className="relative text-xs text-blue-200">Desarrollos Comerciales del Sur, S.A.</p>
      </aside>

      <section className="flex flex-col items-center justify-center gap-6 bg-surface p-6">
        <header className="max-w-md text-center">
          <h2 className="text-xl font-bold uppercase leading-snug tracking-wide text-navy">
            Sistema de Análisis Predictivo basado en Machine Learning
          </h2>
        </header>
        <form
          onSubmit={enviar}
          className="w-full max-w-md space-y-5 rounded-2xl border border-line bg-panel p-8 shadow-[0_8px_30px_rgba(15,37,87,0.08)]"
        >
          <div className="space-y-1">
            <h1 className="text-2xl font-bold text-navy">Bienvenido</h1>
            <p className="text-sm text-muted">Inicie sesión para continuar.</p>
          </div>
          {sesionExpirada && <AlertBanner tipo="info">Su sesión expiró. Inicie sesión de nuevo.</AlertBanner>}
          {error && <AlertBanner>{error}</AlertBanner>}
          <div className="space-y-1.5">
            <label htmlFor="login-email" className="text-xs font-medium text-muted">
              Correo
            </label>
            <div className="relative">
              <Mail aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                id="login-email"
                type="email"
                required
                autoComplete="username"
                placeholder="usuario@empresa.com"
                className="w-full rounded-lg border border-line bg-white py-2.5 pl-10 pr-3 text-sm text-ink placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="login-password" className="text-xs font-medium text-muted">
              Contraseña
            </label>
            <PasswordInput
              id="login-password"
              required
              minLength={8}
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={enviando}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            {enviando ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <LogIn className="h-4 w-4" aria-hidden />}
            {enviando ? 'Ingresando…' : 'Ingresar'}
          </button>
        </form>
      </section>
    </main>
  )
}
