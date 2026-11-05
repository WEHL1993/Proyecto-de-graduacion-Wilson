import path from 'node:path'

import { capturar, expect, iniciarSesion, test } from './apoyo'
import { EXCEL_REAL, EXCEL_SINTETICO, TMP_DIR } from './entorno'

test.describe.serial('Carga de datos históricos (ETL)', () => {
  test.beforeEach(async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/etl')
  })

  const subir = async (page: import('@playwright/test').Page, archivo: string, modo?: string) => {
    await page.getByRole('button', { name: 'Archivo Excel' }).locator('..').locator('input[type=file]').setInputFiles(archivo)
    if (modo) await page.getByLabel('Modo de carga').selectOption({ label: modo })
    await page.getByRole('button', { name: 'Cargar archivo' }).click()
  }

  test('rechaza en el navegador un archivo que no es .xlsx', async ({ page }) => {
    const falso = path.join(TMP_DIR, 'no-es-excel.txt')
    await (await import('node:fs/promises')).writeFile(falso, 'hola')
    await page.locator('input[type=file]').setInputFiles(falso)
    await expect(page.getByText('Solo se admiten archivos Excel (.xlsx).')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cargar archivo' })).toBeDisabled()
  })

  test('carga el Excel comercial real (formato ancho) en modo parcial', async ({ page }) => {
    await subir(page, EXCEL_REAL, 'Parcial: carga las filas válidas')
    const historial = page.getByRole('table', { name: 'Lotes ETL' })
    const fila = historial.getByRole('row', { name: /VENTAS DIARIAS MARZO 2025\.xlsx/ })
    await expect(fila).toBeVisible({ timeout: 60_000 })
    await expect(fila).toContainText('cargado')
    await expect(fila).toContainText('1,267')
    await capturar(page, '05-01-etl-excel-real-cargado')
  })

  test('el mismo archivo no se puede cargar dos veces (checksum)', async ({ page }) => {
    await subir(page, EXCEL_REAL, 'Parcial: carga las filas válidas')
    await expect(page.getByText(/duplicad/i).first()).toBeVisible({ timeout: 30_000 })
    await capturar(page, '05-02-etl-lote-duplicado')
    await expect(page.getByRole('table', { name: 'Lotes ETL' }).getByRole('row', { name: /VENTAS DIARIAS/ })).toHaveCount(1)
  })

  test('carga el histórico sintético en formato tabular (90 días, 720 filas)', async ({ page }) => {
    await subir(page, EXCEL_SINTETICO)
    const fila = page.getByRole('table', { name: 'Lotes ETL' }).getByRole('row', { name: /historico_sintetico\.xlsx/ })
    await expect(fila).toContainText('cargado', { timeout: 60_000 })
    await expect(fila).toContainText('720')
    await capturar(page, '05-03-etl-historial-de-lotes')
  })
})
