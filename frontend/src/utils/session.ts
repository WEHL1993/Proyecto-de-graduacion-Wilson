const CLAVE = 'ds.session'

export interface Sesion {
  token: string
  expiraEn: number // epoch ms
  usuario: { id: string; nombre_completo: string; roles: string[]; permisos: string[] }
}

export function leerSesion(): Sesion | null {
  try {
    const cruda = localStorage.getItem(CLAVE)
    if (!cruda) return null
    const sesion = JSON.parse(cruda) as Sesion
    return sesion.expiraEn > Date.now() ? sesion : null
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
