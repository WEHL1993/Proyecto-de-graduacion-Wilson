import type { AccesoSesion, TokenResponse } from '../types'
import { httpClient } from './httpClient'

export const login = (email: string, password: string) =>
  httpClient.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data)

export const cambiarPassword = (password_actual: string, password_nueva: string) =>
  httpClient.post<void>('/auth/cambiar-password', { password_actual, password_nueva }).then(() => undefined)

/** Roles, permisos y menú vigentes en la BD para el usuario de la sesión. */
export const sesionVigente = () => httpClient.get<AccesoSesion>('/auth/me').then((r) => r.data)
