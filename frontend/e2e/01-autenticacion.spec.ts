import { capturar, expect, iniciarSesion, test } from './apoyo'

const PANTALLAS_ADMIN = [
  ['Dashboard de Ventas', /Dashboard de Ventas/],
  ['Liquidación Diaria', /Liquidación diaria de ventas/],
  ['Historial de Liquidaciones', /Historial de liquidaciones/],
  ['Abastecimiento', /Abastecimiento y Pedidos/],
  ['Recepción de mercadería', /Recepción de mercadería/],
  ['Inventario y Kardex', /Inventario y Kardex/],
  ['Productos', /^Productos$/],
  ['Reportes', /Reportes gerenciales/],
  ['Monitoreo de Modelos', /Monitoreo de Modelos ML/],
  ['Rutas', /Rutas y equipos/],
  ['Carga de Datos (ETL)', /Carga de datos históricos \(ETL\)/],
  ['Política de Datos', /Política de datos del modelo/],
  ['Usuarios y Roles', /Usuarios y roles/],
] as const

test.describe('Autenticación y navegación', () => {
  test('una ruta protegida sin sesión redirige al login', async ({ page }) => {
    await page.goto('/productos')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
    await capturar(page, '01-01-login')
  })

  test('credenciales incorrectas muestran un error y no inician sesión', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Correo').fill('admin@ds.gt')
    await page.getByLabel('Contraseña', { exact: true }).fill('ClaveIncorrecta1')
    await page.getByRole('button', { name: 'Ingresar' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await capturar(page, '01-02-login-credenciales-incorrectas')
    await expect(page).toHaveURL(/\/login/)
  })

  test('el botón de mostrar contraseña alterna su visibilidad', async ({ page }) => {
    await page.goto('/login')
    const clave = page.getByLabel('Contraseña', { exact: true })
    await expect(clave).toHaveAttribute('type', 'password')
    await page.getByRole('button', { name: 'Mostrar contraseña' }).click()
    await expect(clave).toHaveAttribute('type', 'text')
  })

  test('el Administrador ve las 13 pantallas del menú y todas cargan', async ({ page }) => {
    await iniciarSesion(page)
    await expect(page.getByRole('heading', { name: 'Dashboard de Ventas', level: 1 })).toBeVisible()
    await capturar(page, '01-03-inicio-administrador-menu-completo')
    for (const [enlace, titulo] of PANTALLAS_ADMIN) {
      await page.getByRole('link', { name: enlace, exact: true }).click()
      await expect(page.getByRole('heading', { level: 1, name: titulo })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toHaveCount(0)
    }
  })

  test('la sesión sobrevive a una recarga y cerrar sesión la termina', async ({ page }) => {
    await iniciarSesion(page)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Dashboard de Ventas', level: 1 })).toBeVisible()
    await page.getByRole('button', { name: /Administrador del Sistema/ }).click()
    await capturar(page, '01-04-menu-de-usuario')
    await page.getByRole('menuitem', { name: 'Cerrar sesión' }).click()
    await expect(page).toHaveURL(/\/login/)
    await page.goto('/usuarios')
    await expect(page).toHaveURL(/\/login/)
  })

  test('una ruta inexistente vuelve al inicio', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/no-existe')
    await expect(page).toHaveURL(/\/$/)
  })
})
