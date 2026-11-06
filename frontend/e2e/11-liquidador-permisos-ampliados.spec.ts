import type { Page } from '@playwright/test'

import { capturar, expect, FECHA_OPERACION, iniciarSesion, test, toast } from './apoyo'

/**
 * Caso real de la empresa: el Administrador amplía, desde la matriz de permisos, lo que puede
 * hacer el rol Liquidador, y crea la cuenta liquidador@ds.gt (Oscar Herrarte).
 * Los permisos reproducen el menú que tiene ese usuario en la instalación local.
 */
const OSCAR = {
  email: 'liquidador@ds.gt',
  nombre: 'Oscar Herrarte',
  temporal: 'Liquidador2026!',
  nueva: 'HerrarteO26',
}
const PERMISOS_EXTRA = ['carga_ruta:generar', 'pedido_proveedor:gestionar', 'inventario:leer', 'reportes:leer']
const MENU_ESPERADO = [
  'Dashboard de Ventas',
  'Liquidación Diaria',
  'Historial de Liquidaciones',
  'Abastecimiento',
  'Inventario y Kardex',
  'Productos',
  'Reportes',
]
const SIN_ACCESO = ['Recepción de mercadería', 'Monitoreo de Modelos', 'Rutas', 'Carga de Datos (ETL)', 'Política de Datos', 'Usuarios y Roles']

async function menu(page: Page) {
  return page.getByRole('navigation').first()
}

test.describe.serial('Liquidador con permisos ampliados (liquidador@ds.gt)', () => {
  test('el Administrador amplía los permisos del rol Liquidador en la matriz', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/usuarios')
    await page.getByRole('tab', { name: 'Matriz de permisos' }).click()
    for (const codigo of PERMISOS_EXTRA) {
      const casilla = page.getByRole('checkbox', { name: `Liquidador · ${codigo}`, exact: true })
      await expect(casilla).not.toBeChecked()
      await casilla.check()
    }
    await capturar(page, '11-01-matriz-liquidador-ampliado')
    // El contador cuenta roles modificados (aquí, 1: Liquidador), no permisos.
    const guardado = page.waitForResponse((r) => /\/rbac\/roles\/[^/]+\/permissions$/.test(r.url()) && r.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Guardar cambios (1)' }).click()
    expect((await guardado).ok()).toBe(true)
    await page.reload()
    await page.getByRole('tab', { name: 'Matriz de permisos' }).click()
    for (const codigo of PERMISOS_EXTRA) {
      await expect(page.getByRole('checkbox', { name: `Liquidador · ${codigo}`, exact: true })).toBeChecked()
    }
  })

  test('crea la cuenta liquidador@ds.gt con contraseña temporal', async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/usuarios')
    await page.getByRole('button', { name: '+ Nuevo usuario' }).click()
    const d = page.getByRole('dialog', { name: 'Nuevo usuario' })
    await d.getByLabel('Correo electrónico').fill(OSCAR.email)
    await d.getByLabel('Nombre completo').fill(OSCAR.nombre)
    await d.getByRole('textbox', { name: /^Contraseña/ }).fill(OSCAR.temporal)
    await d.getByRole('checkbox', { name: 'Liquidador' }).check()
    await d.getByRole('checkbox', { name: 'CORNELIO · Cornelio' }).check()
    await d.getByRole('button', { name: 'Crear usuario' }).click()
    await expect(d).toBeHidden()
    await expect(page.getByRole('row', { name: new RegExp(OSCAR.nombre) })).toBeVisible()
  })

  test('Oscar entra con Liquidador2026! y la cambia a HerrarteO26', async ({ page }) => {
    await iniciarSesion(page, OSCAR.email, OSCAR.temporal)
    await expect(page).toHaveURL(/\/cambiar-password/)
    await page.getByRole('textbox', { name: 'Contraseña temporal' }).fill(OSCAR.temporal)
    await page.getByRole('textbox', { name: 'Nueva contraseña (mínimo 8 caracteres)' }).fill(OSCAR.nueva)
    await page.getByRole('textbox', { name: 'Confirmar nueva contraseña' }).fill(OSCAR.nueva)
    await capturar(page, '11-02a-cambio-contrasena-liquidador')
    await page.getByRole('button', { name: 'Guardar contraseña' }).click()
    await expect(page).not.toHaveURL(/\/cambiar-password/)

    // La contraseña anterior ya no sirve; la nueva sí.
    await page.getByRole('button', { name: new RegExp(OSCAR.nombre) }).click()
    await page.getByRole('menuitem', { name: 'Cerrar sesión' }).click()
    await page.getByLabel('Correo').fill(OSCAR.email)
    await page.getByLabel('Contraseña', { exact: true }).fill(OSCAR.temporal)
    await page.getByRole('button', { name: 'Ingresar' }).click()
    await expect(page.getByRole('alert').first()).toBeVisible()
    await iniciarSesion(page, OSCAR.email, OSCAR.nueva)
  })

  test('su menú tiene las 7 pantallas de sus permisos y ninguna más', async ({ page }) => {
    await iniciarSesion(page, OSCAR.email, OSCAR.nueva)
    const nav = await menu(page)
    for (const etiqueta of MENU_ESPERADO) await expect(nav.getByRole('link', { name: etiqueta, exact: true })).toBeVisible()
    for (const etiqueta of SIN_ACCESO) await expect(nav.getByRole('link', { name: etiqueta, exact: true })).toHaveCount(0)
    await capturar(page, '11-02-menu-liquidador-ampliado')
    for (const ruta of ['/recepcion', '/usuarios', '/etl', '/monitoreo']) {
      await page.goto(ruta)
      await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toBeVisible()
    }
    await capturar(page, '11-02b-acceso-denegado-liquidador')
  })

  test('puede generar un plan de carga pero no aprobarlo', async ({ page }) => {
    await iniciarSesion(page, OSCAR.email, OSCAR.nueva)
    await page.goto('/')
    const ruta = page.getByLabel('Ruta')
    await expect(ruta).not.toHaveValue('')
    await ruta.selectOption({ label: 'CORNELIO Cornelio' })
    await page.getByLabel('Fecha operación').fill(FECHA_OPERACION)
    await page.getByRole('button', { name: 'Consultar' }).click()
    await page.getByRole('button', { name: 'Generar plan sugerido' }).click()
    await expect(toast(page, 'Plan generado en borrador.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Enviar a aprobación' })).toBeVisible()
    await expect(page.getByRole('button', { name: '✔ Aprobar' })).toHaveCount(0)
    await capturar(page, '11-03-dashboard-liquidador-genera-plan')
  })

  test('consulta abastecimiento, inventario, productos y reportes en modo lectura', async ({ page }) => {
    await iniciarSesion(page, OSCAR.email, OSCAR.nueva)
    await page.goto('/compras')
    await expect(page.getByRole('heading', { level: 1, name: 'Abastecimiento y Pedidos' })).toBeVisible()
    await capturar(page, '11-04-abastecimiento-liquidador')

    await page.goto('/inventario')
    await expect(page.getByRole('heading', { level: 1, name: 'Inventario y Kardex' })).toBeVisible()
    await capturar(page, '11-05-inventario-liquidador')

    await page.goto('/productos')
    await expect(page.getByRole('heading', { level: 1, name: 'Productos' })).toBeVisible()
    // Sin productos:crear|editar|eliminar ni inventario:ajustar: solo consulta.
    await expect(page.getByRole('button', { name: '+ Nuevo producto' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Ajustar stock de / })).toHaveCount(0)
    await capturar(page, '11-06-productos-liquidador-solo-lectura')

    await page.goto('/reportes')
    await expect(page.getByRole('region', { name: 'Indicadores' })).toBeVisible()
    await capturar(page, '11-07-reportes-liquidador')
  })

  test('sigue pudiendo registrar la liquidación de su ruta', async ({ page }) => {
    await iniciarSesion(page, OSCAR.email, OSCAR.nueva)
    await page.goto('/ventas/liquidacion')
    await page.getByLabel('Fecha').fill(FECHA_OPERACION)
    await page.getByLabel('Ruta').selectOption({ label: 'CORNELIO · Cornelio' })
    await expect(page.getByRole('table', { name: 'Unidades por presentación' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Guardar borrador' })).toBeVisible()
    await capturar(page, '11-08-liquidacion-liquidador')
  })
})
