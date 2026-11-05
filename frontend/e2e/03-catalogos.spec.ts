import { capturar, expect, iniciarSesion, test, toast } from './apoyo'

test.describe.serial('Catálogos: rutas, personal y equipos', () => {
  test.beforeEach(async ({ page }) => iniciarSesion(page))

  test('crea una ruta (el código se guarda en mayúsculas) y la edita', async ({ page }) => {
    await page.goto('/catalogos/rutas')
    await page.getByRole('button', { name: '+ Nueva ruta' }).click()
    const dialogo = page.getByRole('dialog', { name: 'Nueva ruta' })
    await dialogo.getByLabel('Código').fill('e2e-norte')
    await dialogo.getByLabel('Nombre').fill('Ruta Norte E2E')
    await dialogo.getByLabel('Zona (opcional)').fill('Zona 18')
    await dialogo.getByRole('button', { name: 'Crear ruta' }).click()
    await expect(dialogo).toBeHidden()
    const fila = page.getByRole('row', { name: /E2E-NORTE/ })
    await expect(fila).toContainText('Ruta Norte E2E')
    await expect(fila).toContainText('Zona 18')
    await capturar(page, '03-01-ruta-creada')

    await page.getByRole('button', { name: 'Editar E2E-NORTE' }).click()
    const edicion = page.getByRole('dialog')
    await expect(edicion.getByLabel('Código')).toBeDisabled()
    await edicion.getByLabel('Nombre').fill('Ruta Norte E2E (editada)')
    await edicion.getByRole('button', { name: /Guardar/ }).click()
    await expect(page.getByRole('row', { name: /E2E-NORTE/ })).toContainText('(editada)')
  })

  test('no admite un código de ruta duplicado', async ({ page }) => {
    await page.goto('/catalogos/rutas')
    await page.getByRole('button', { name: '+ Nueva ruta' }).click()
    const dialogo = page.getByRole('dialog', { name: 'Nueva ruta' })
    await dialogo.getByLabel('Código').fill('CESAR')
    await dialogo.getByLabel('Nombre').fill('Duplicada')
    await dialogo.getByRole('button', { name: 'Crear ruta' }).click()
    await expect(toast(page, 'Ya existe una ruta con ese código.')).toBeVisible()
    await expect(dialogo).toBeVisible()
  })

  test('da de alta el personal de ruta', async ({ page }) => {
    await page.goto('/catalogos/empleados')
    for (const nombre of ['Vendedor E2E', 'Chofer E2E']) {
      await page.getByRole('button', { name: '+ Nuevo empleado' }).click()
      const dialogo = page.getByRole('dialog', { name: 'Nuevo empleado' })
      await dialogo.getByLabel('Nombre completo').fill(nombre)
      await dialogo.getByRole('button', { name: 'Crear empleado' }).click()
      await expect(dialogo).toBeHidden()
      await expect(page.getByRole('row', { name: new RegExp(nombre) })).toBeVisible()
    }
    await capturar(page, '03-03-personal-de-ruta')
  })

  test('el equipo de ruta exige un reparto que sume 100 % y luego se guarda', async ({ page }) => {
    await page.goto('/catalogos/rutas')
    await page.getByRole('link', { name: 'Equipo de E2E-NORTE' }).click()
    await expect(page.getByRole('heading', { level: 1, name: /Equipo de la ruta E2E-NORTE/ })).toBeVisible()

    await page.getByLabel('Empleado 1').selectOption({ label: 'Vendedor E2E' })
    await page.getByLabel('Porcentaje 1').fill('60')
    await page.getByRole('button', { name: '+ Agregar integrante' }).click()
    await page.getByLabel('Empleado 2').selectOption({ label: 'Chofer E2E' })
    await page.getByLabel('Rol 2').selectOption({ label: 'Chofer' })
    await page.getByLabel('Porcentaje 2').fill('30')
    await expect(page.getByRole('status')).toContainText('faltan 10.00')
    await page.getByRole('button', { name: 'Guardar equipo' }).click()
    await expect(page.getByText('Los porcentajes deben sumar exactamente 100,00 (suman 90.00).')).toBeVisible()

    await page.getByLabel('Porcentaje 2').fill('40')
    await expect(page.getByRole('status')).toContainText('100.00 %')
    await capturar(page, '03-02-equipo-de-ruta-reparto-100')
    await page.getByRole('button', { name: 'Guardar equipo' }).click()

    await page.goto('/catalogos/rutas')
    await expect(page.getByRole('row', { name: /E2E-NORTE/ })).toContainText('2 integrantes · 100.00 %')
  })

  test('desactivar una ruta la oculta hasta mostrar las inactivas', async ({ page }) => {
    await page.goto('/catalogos/rutas')
    await page.getByRole('button', { name: 'Desactivar E2E-NORTE' }).click()
    const confirmar = page.getByRole('dialog')
    if (await confirmar.isVisible()) await confirmar.getByRole('button', { name: /Desactivar|Confirmar/ }).click()
    await expect(page.getByRole('row', { name: /E2E-NORTE/ })).toHaveCount(0)
    await page.getByLabel('Mostrar rutas inactivas').check()
    await expect(page.getByRole('row', { name: /E2E-NORTE/ })).toBeVisible()
    await capturar(page, '03-04-rutas-inactivas')
    await page.getByRole('button', { name: 'Activar E2E-NORTE' }).click()
    await expect(page.getByRole('button', { name: 'Desactivar E2E-NORTE' })).toBeVisible()
  })
})
