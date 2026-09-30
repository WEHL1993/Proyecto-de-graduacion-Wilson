import type { TokenResponse } from '../types'
import { httpClient } from './httpClient'

export const login = (email: string, password: string) =>
  httpClient.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data)
