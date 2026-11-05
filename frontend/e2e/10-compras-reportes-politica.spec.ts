import { readFile } from 'node:fs/promises'

import { capturar, expect, iniciarSesion, test } from './apoyo'

test.describe.serial('Abastecimiento, reportes, política de datos y alertas', () => {
  test.beforeEach(async ({ page }) => iniciarSesion(page))

  test('las sugerencias de compra usan la demanda proyectada', async ({ page }) => {
    await page.goto('/compras')
    await expect(page.getByText('Cantidad a pedir = máx(0, (demanda proyectada + stock mínimo) − stock disponible).')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Sugerencias sin proveedor' })).toBeVisible({ timeout: 30_000 })
    await capturar(page, '10-01-sugerencias-de-compra')
    await page.getByLabel('Horizonte de demanda').selectOption({ label: 'Próximos 14 días' })
    await expect(page.getByRole('region', { name: 'Sugerencias sin proveedor' })).toBeVisible({ timeout: 30_000 })
  })

  test('los reportes muestran indicadores, aplican filtros y exportan CSV', async ({ page }) => {
    await page.goto('/reportes')
    const indicadores = page.getByRole('region', { name: 'Indicadores' })
    await expect(indicadores).toContainText('Venta real (uds)')
    await page.getByLabel('Desde').fill('2025-03-01')
    await page.getByLabel('Hasta').fill('2025-04-01')
    await page.getByRole('combobox', { name: 'Ruta' }).selectOption({ label: 'CESAR · Cesar' })
    await page.getByRole('button', { name: 'Aplicar' }).click()
    await expect(page.getByText(/Periodo: 2025-03-01 → 2025-04-01/)).toBeVisible()
    await capturar(page, '10-02-reportes-gerenciales', { completa: true })

    const descarga = page.waitForEvent('download')
    await page.getByRole('button', { name: '⬇ CSV' }).click()
    const archivo = await descarga
    expect(archivo.suggestedFilename()).toMatch(/\.csv$/)
    const contenido = await readFile((await archivo.path())!, 'utf-8')
    expect(contenido.length).toBeGreaterThan(20)

    const excel = page.waitForEvent('download')
    await page.getByRole('button', { name: '⬇ Excel (consolidado)' }).click()
    expect((await excel).suggestedFilename()).toMatch(/\.xlsx$/)
  })

  test('cambia el umbral de diferencia de caja y persiste', async ({ page }) => {
    await page.goto('/politica-datos')
    await page.getByLabel('Umbral de diferencia de caja').fill('25')
    await page.getByRole('button', { name: 'Guardar umbral' }).click()
    await page.reload()
    await expect(page.getByLabel('Umbral de diferencia de caja')).toHaveValue('25')
  })

  test('cerrar el arranque deshabilita la carga de Excel y se puede reabrir', async ({ page }) => {
    await page.goto('/politica-datos')
    await expect(page.getByText('habilitada (arranque abierto)')).toBeVisible()
    await capturar(page, '10-02b-politica-de-datos')
    await page.getByRole('button', { name: 'Cerrar arranque' }).click()
    await capturar(page, '10-02c-confirmar-cierre-del-arranque')
    const confirmar = page.getByRole('dialog')
    await confirmar.getByRole('button', { name: /Cerrar arranque|Confirmar/ }).click()
    await expect(page.getByText(/deshabilitada/)).toBeVisible()

    await page.goto('/etl')
    await expect(page.getByText('Carga de Excel deshabilitada.')).toBeVisible()
    await capturar(page, '10-03-etl-deshabilitado-por-politica')

    await page.goto('/politica-datos')
    await page.getByRole('button', { name: /Reabrir/ }).click()
    const reabrir = page.getByRole('dialog')
    if (await reabrir.isVisible()) await reabrir.getByRole('button', { name: /Reabrir|Confirmar/ }).click()
    await expect(page.getByText('habilitada (arranque abierto)')).toBeVisible()
  })

  test('la campana lista las alertas abiertas y permite reconocerlas', async ({ page }) => {
    await page.goto('/')
    const campana = page.getByRole('button', { name: /\d+ alertas/ })
    await expect(campana).not.toHaveAccessibleName('0 alertas')
    await campana.click()
    await capturar(page, '10-04-alertas')
    await expect(page.getByText(/stock|quiebre|caja/i).first()).toBeVisible()
  })
})
