/** Fixtures y utilidades compartidas por las pruebas E2E. */
import { expect, test as base, type Page } from '@playwright/test'

import { ADMIN } from './entorno'

type Fallos = { erroresJs: string[]; errores5xx: string[] }

/**
 * `test` con vigilancia: cualquier error JavaScript no capturado en la página o respuesta 5xx de
 * la API hace fallar la prueba, aunque sus aserciones hayan pasado.
 */
export const test = base.extend<{ fallos: Fallos }>({
  fallos: [
    async ({ page }, use) => {
      const fallos: Fallos = { erroresJs: [], errores5xx: [] }
      page.on('pageerror', (e) => fallos.erroresJs.push(e.message))
      page.on('response', (r) => {
        if (r.url().includes('/api/') && r.status() >= 500) {
          fallos.errores5xx.push(`${r.status()} ${r.request().method()} ${r.url()}`)
        }
      })
      await use(fallos)
      expect(fallos.erroresJs, 'errores JavaScript no capturados').toEqual([])
      expect(fallos.errores5xx, 'respuestas 5xx de la API').toEqual([])
    },
    { auto: true },
  ],
})
export { expect }

export async function iniciarSesion(page: Page, email = ADMIN.email, password = ADMIN.password) {
  await page.goto('/login')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

/** Navega por el menú lateral (como un usuario), no por URL. */
export async function irPorMenu(page: Page, etiqueta: string) {
  await page.getByRole('link', { name: etiqueta, exact: true }).click()
}

/** Fecha de operación fija: el día siguiente al último dato real (Excel de marzo 2025). */
export const FECHA_OPERACION = '2025-04-01'

/** Los errores y avisos de la app se muestran como *toasts* (role alert/status) fuera del modal. */
export const toast = (page: Page, texto: string | RegExp) =>
  page.getByRole('alert').or(page.getByRole('status')).filter({ hasText: texto }).first()
