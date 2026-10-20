import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, ShieldCheck } from 'lucide-react'
import { useAuth } from '../app/providers/AuthProvider'
import { PasswordInput } from '../components/common/PasswordInput'
import { AlertBanner } from '../components/feedback/feedback'
import { useToast } from '../components/feedback/toast'
import { apiError, mensajeError } from '../utils/errors'

export interface FormPassword {
  actual: string
  nueva: string
  confirmacion: string
}

/** Errores por campo; vacío = válido. */
export function validarPassword(f: FormPassword): Partial<Record<keyof FormPassword, string>> {
  const e: Partial<Record<keyof FormPassword, string>> = {}
  if (!f.actual) e.actual = 'Ingrese su contraseña actual.'
  if (f.nueva.length < 8) e.nueva = 'Mínimo 8 caracteres.'
  else if (f.nueva === f.actual) e.nueva = 'Debe ser distinta de la actual.'
  if (f.confirmacion !== f.nueva) e.confirmacion = 'Las contraseñas no coinciden.'
  return e
}

/** Cambio de contraseña propio. Con contraseña temporal es el único paso permitido tras ingresar. */
export function CambiarPasswordView() {
  const { usuario, cambiarPassword, logout } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const obligatorio = usuario?.debe_cambiar_password === true
  const [form, setForm] = useState<FormPassword>({ actual: '', nueva: '', confirmacion: '' })
  const [intento, setIntento] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const errores = validarPassword(form)
  const set = (k: keyof FormPassword, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const enviar = async (ev: FormEvent) => {
    ev.preventDefault()
    setIntento(true)
    setError(null)
    if (Object.keys(errores).length) return
    setEnviando(true)
    try {
      await cambiarPassword(form.actual, form.nueva)
      toast.exito('Contraseña actualizada.')
      navigate(usuario?.pantalla_inicio ?? '/', { replace: true })
    } catch (err) {
      setError(apiError(err)?.mensaje ?? mensajeError(err))
    } finally {
      setEnviando(false)
    }
  }

  const campo = (k: keyof FormPassword, id: string, etiqueta: string, autoComplete: string) => (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {etiqueta}
      </label>
      <PasswordInput
        id={id}
        autoComplete={autoComplete}
        value={form[k]}
        onChange={(e) => set(k, e.target.value)}
      />
      {intento && errores[k] && (
        <span role="alert" className="text-xs text-bad">
          {errores[k]}
        </span>
      )}
    </div>
  )

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-surface p-6">
      <form
        onSubmit={enviar}
        noValidate
        className="w-full max-w-md space-y-5 rounded-2xl border border-line bg-panel p-8 shadow-[0_8px_30px_rgba(15,37,87,0.08)]"
      >
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-bold text-navy">
            <ShieldCheck className="h-6 w-6" aria-hidden />
            Cambiar contraseña
          </h1>
          <p className="text-sm text-muted">
            {obligatorio
              ? 'Su contraseña es temporal. Defina una nueva para continuar.'
              : 'Ingrese su contraseña actual y elija una nueva.'}
          </p>
        </div>
        {obligatorio && (
          <AlertBanner tipo="info">Por seguridad, debe cambiar la contraseña asignada por el administrador.</AlertBanner>
        )}
        {error && <AlertBanner>{error}</AlertBanner>}
        {campo('actual', 'pw-actual', obligatorio ? 'Contraseña temporal' : 'Contraseña actual', 'current-password')}
        {campo('nueva', 'pw-nueva', 'Nueva contraseña (mínimo 8 caracteres)', 'new-password')}
        {campo('confirmacion', 'pw-confirmacion', 'Confirmar nueva contraseña', 'new-password')}
        <button
          type="submit"
          disabled={enviando}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand disabled:cursor-not-allowed disabled:opacity-60"
        >
          {enviando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          {enviando ? 'Guardando…' : 'Guardar contraseña'}
        </button>
        {obligatorio ? (
          <button type="button" onClick={logout} className="w-full text-center text-sm text-muted hover:text-ink">
            Cerrar sesión
          </button>
        ) : (
          <Link to="/" className="flex items-center justify-center gap-1.5 text-sm text-muted hover:text-ink">
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Volver
          </Link>
        )}
      </form>
    </main>
  )
}
