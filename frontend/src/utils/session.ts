import type { PantallaMenu } from '../types'

const CLAVE = 'ds.session'

export interface Sesion {
  token: string
  expiraEn: number // epoch ms
  /** Roles, permisos y menú vienen de la BD (ADR-19); se refrescan con `GET /auth/me`. */
  usuario: {
    id: string
    nombre_completo: string
    roles: string[]
    permisos: string[]
    menu: PantallaMenu[]
    pantalla_inicio: string | null
    /** Contraseña temporal fijada por un administrador: obliga a cambiarla antes de operar. */
    debe_cambiar_password?: boolean
  }
}

export function leerSesion(): Sesion | null {
  try {
    const cruda = localStorage.getItem(CLAVE)
    if (!cruda) return null
    const sesion = JSON.parse(cruda) as Sesion
    if (sesion.expiraEn <= Date.now()) return null
    // Sesiones guardadas antes de la ADR-19 no traen menú: se completa al refrescar.
    sesion.usuario.menu ??= []
    sesion.usuario.pantalla_inicio ??= null
    return sesion
  } catch {
    return null
  }
}

export function guardarSesion(sesion: Sesion): void {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(sesion))
  } catch {
    /* almacenamiento bloqueado: la sesión vive solo en memoria */
  }
}

export function borrarSesion(): void {
  try {
    localStorage.removeItem(CLAVE)
  } catch {
    /* nada que borrar */
  }
}
