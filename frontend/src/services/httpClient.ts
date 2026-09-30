import axios from 'axios'
import { borrarSesion, leerSesion } from '../utils/session'

export const httpClient = axios.create({ baseURL: '/api/v1', timeout: 30_000 })

// Callback que registra el AuthProvider para reaccionar a un 401 (token vencido o inválido).
let alExpirar: (() => void) | null = null
export const registrarAlExpirar = (fn: (() => void) | null): void => {
  alExpirar = fn
}

httpClient.interceptors.request.use((config) => {
  const sesion = leerSesion()
  if (sesion) config.headers.Authorization = `Bearer ${sesion.token}`
  return config
})

httpClient.interceptors.response.use(
  (r) => r,
  (error) => {
    // El login devuelve 401 por credenciales erróneas: eso no es una sesión vencida.
    const esLogin = String(error.config?.url ?? '').includes('/auth/login')
    if (error.response?.status === 401 && !esLogin) {
      borrarSesion()
      alExpirar?.()
    }
    return Promise.reject(error)
  },
)
