import { expect, iniciarSesion, test, toast } from './apoyo'

export const LIQUIDADOR = {
  email: 'liquidador.e2e@ds.gt',
  nombre: 'Liquidador E2E',
  temporal: 'Temporal123',
  definitiva: 'Definitiva456',
}

test.describe.serial('Usuarios, roles y permisos', () => {
  test('el Administrador crea un usuario Liquidador con contraseña temporal', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/usuarios')
    await page.getByRole('button', { name: '+ Nuevo usuario' }).click()
    const dialogo = page.getByRole('dialog', { name: 'Nuevo usuario' })
    await dialogo.getByLabel('Correo electrónico').fill(LIQUIDADOR.email)
    await dialogo.getByLabel('Nombre completo').fill(LIQUIDADOR.nombre)
    await dialogo.getByRole('textbox', { name: /^Contraseña/ }).fill(LIQUIDADOR.temporal)
    await dialogo.getByRole('checkbox', { name: 'Liquidador' }).check()
    await dialogo.getByRole('checkbox', { name: 'CESAR · Cesar' }).check()
    await dialogo.getByRole('button', { name: 'Crear usuario' }).click()
    await expect(dialogo).toBeHidden()
    const fila = page.getByRole('row', { name: new RegExp(LIQUIDADOR.nombre) })
    await expect(fila).toBeVisible()
    await expect(fila).toContainText('CESAR')
  })

  test('no permite registrar dos usuarios con el mismo correo', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/usuarios')
    await page.getByRole('button', { name: '+ Nuevo usuario' }).click()
    const dialogo = page.getByRole('dialog', { name: 'Nuevo usuario' })
    await dialogo.getByLabel('Correo electrónico').fill(LIQUIDADOR.email)
    await dialogo.getByLabel('Nombre completo').fill('Duplicado')
    await dialogo.getByRole('textbox', { name: /^Contraseña/ }).fill('OtraClave123')
    await dialogo.getByRole('checkbox', { name: 'Gerente' }).check()
    await dialogo.getByRole('button', { name: 'Crear usuario' }).click()
    await expect(toast(page, /correo/i)).toBeVisible()
    await expect(dialogo).toBeVisible()
  })

  test('el Liquidador debe cambiar la contraseña temporal en su primer ingreso', async ({ page }) => {
    await iniciarSesion(page, LIQUIDADOR.email, LIQUIDADOR.temporal)
    await expect(page).toHaveURL(/\/cambiar-password/)
    await expect(page.getByText('Su contraseña es temporal. Defina una nueva para continuar.')).toBeVisible()
    await page.getByRole('textbox', { name: 'Contraseña temporal' }).fill(LIQUIDADOR.temporal)
    await page.getByRole('textbox', { name: 'Nueva contraseña (mínimo 8 caracteres)' }).fill(LIQUIDADOR.definitiva)
    await page.getByRole('textbox', { name: 'Confirmar nueva contraseña' }).fill(LIQUIDADOR.definitiva)
    await page.getByRole('button', { name: 'Guardar contraseña' }).click()
    await expect(page).toHaveURL(/\/ventas\/liquidacion/)
  })

  test('el Liquidador solo ve sus pantallas y el resto responde «Acceso denegado»', async ({ page }) => {
    await iniciarSesion(page, LIQUIDADOR.email, LIQUIDADOR.definitiva)
    const menu = page.getByRole('navigation').first()
    await expect(menu.getByRole('link', { name: 'Liquidación Diaria' })).toBeVisible()
    await expect(menu.getByRole('link', { name: 'Usuarios y Roles' })).toHaveCount(0)
    await expect(menu.getByRole('link', { name: 'Productos' })).toHaveCount(0)
    for (const ruta of ['/usuarios', '/productos', '/etl', '/monitoreo']) {
      await page.goto(ruta)
      await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toBeVisible()
    }
  })

  test('la matriz de permisos y el acceso por pantalla se muestran al Administrador', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/usuarios')
    await page.getByRole('tab', { name: 'Matriz de permisos' }).click()
    await expect(page.getByText('usuarios:gestionar').first()).toBeVisible()
    await page.getByRole('tab', { name: 'Acceso por pantalla' }).click()
    await expect(page.getByText('Dashboard de Ventas').first()).toBeVisible()
  })

  test('filtrar usuarios por rol muestra solo los de ese rol', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/usuarios')
    await page.getByLabel('Rol').selectOption('Liquidador')
    await expect(page.getByRole('row', { name: new RegExp(LIQUIDADOR.nombre) })).toBeVisible()
    await expect(page.getByRole('row', { name: /Administrador del Sistema/ })).toHaveCount(0)
  })
})
