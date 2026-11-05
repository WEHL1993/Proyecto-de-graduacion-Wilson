import type { Page } from '@playwright/test'

import { capturar, expect, FECHA_OPERACION, iniciarSesion, test } from './apoyo'

async function abrir(page: Page, ruta = 'CESAR · Cesar') {
  await page.goto('/ventas/liquidacion')
  await page.getByLabel('Fecha').fill(FECHA_OPERACION)
  await page.getByLabel('Ruta').selectOption({ label: ruta })
  await expect(page.getByRole('table', { name: 'Unidades por presentación' })).toBeVisible()
}

async function unidades(page: Page, sku: string, v: { cargado: string; vendido: string; devuelto?: string; merma?: string }) {
  await page.getByLabel(`Cargado ${sku}`, { exact: true }).fill(v.cargado)
  await page.getByLabel(`Vendido ${sku}`, { exact: true }).fill(v.vendido)
  if (v.devuelto) await page.getByLabel(`Devuelto ${sku}`, { exact: true }).fill(v.devuelto)
  if (v.merma) await page.getByLabel(`Merma ${sku}`, { exact: true }).fill(v.merma)
}

test.describe.serial('Liquidación diaria de ventas', () => {
  test.beforeEach(async ({ page }) => iniciarSesion(page))

  test('marca la fila que no cuadra (vendido + devuelto + merma > cargado)', async ({ page }) => {
    await abrir(page)
    await unidades(page, '500179', { cargado: '10', vendido: '12' })
    await expect(page.getByRole('row', { name: /^500179/ })).toContainText('🔴 Excede')
    await capturar(page, '09-01-liquidacion-fila-que-no-cuadra')
    await unidades(page, '500179', { cargado: '10', vendido: '6' })
    await expect(page.getByRole('row', { name: /^500179/ })).toContainText('🟡 Faltan')
  })

  test('guarda un borrador y lo cierra con unidades y dinero cuadrados', async ({ page }) => {
    await abrir(page)
    // Precios del catálogo: 30 × Q56 = Q1,680 ; 20 × Q27 = Q540 → venta Q2,220
    await unidades(page, '500179', { cargado: '35', vendido: '30', devuelto: '4', merma: '1' })
    await unidades(page, '599033', { cargado: '20', vendido: '20' })
    await expect(page.getByRole('row', { name: /^500179/ })).toContainText('🟢 Cuadra')
    await page.getByRole('checkbox', { name: 'Solo con movimiento' }).check()
    await capturar(page, '09-02-liquidacion-unidades')

    await page.getByRole('button', { name: '2 · Dinero' }).click()
    await page.getByLabel('Efectivo', { exact: true }).fill('1500')
    await page.getByLabel('Transferencia', { exact: true }).fill('720')
    await page.getByLabel('Efectivo entregado', { exact: true }).fill('1500')
    await capturar(page, '09-03-liquidacion-dinero')

    await page.getByRole('button', { name: 'Guardar borrador' }).click()
    await expect(page.getByText(/borrador/i).first()).toBeVisible()

    await page.getByRole('button', { name: 'Cerrar liquidación' }).click()
    const d = page.getByRole('dialog', { name: 'Cerrar liquidación' })
    await expect(d).toContainText('50 unidades')
    await d.getByRole('button', { name: 'Confirmar' }).click()
    await expect(page.getByRole('button', { name: 'Corregir liquidación' })).toBeVisible()
    await capturar(page, '09-04-liquidacion-cerrada')
  })

  test('el historial muestra la liquidación cerrada con su detalle', async ({ page }) => {
    await page.goto('/ventas/liquidaciones')
    const fila = page.getByRole('row', { name: /^2025-04-01 Cesar/ })
    await expect(fila).toContainText('cerrada')
    await expect(fila).toContainText('Q 2,220')
    await expect(fila).toContainText('Liquidador E2E') // vendedor = usuario asignado a la ruta (02)
    await capturar(page, '09-04b-historial-de-liquidaciones')
    await fila.getByRole('button', { name: /Ver detalle/ }).click()
    await expect(page.getByRole('dialog')).toContainText('500179')
    await capturar(page, '09-05-historial-detalle')
  })

  test('corregir exige un motivo de al menos 5 caracteres', async ({ page }) => {
    await abrir(page)
    await unidades(page, '599033', { cargado: '20', vendido: '19', devuelto: '1' })
    await page.getByRole('button', { name: '2 · Dinero' }).click()
    // Una unidad menos vendida (Q27): la transferencia baja a Q693 para seguir cuadrando.
    await page.getByLabel('Transferencia', { exact: true }).fill('693')
    await page.getByRole('button', { name: 'Corregir liquidación' }).click()
    const d = page.getByRole('dialog', { name: 'Corregir liquidación' })
    await d.getByLabel('Motivo').fill('abc')
    await expect(d.getByRole('button', { name: 'Confirmar' })).toBeDisabled()
    await d.getByLabel('Motivo').fill('Devolución no registrada')
    await capturar(page, '09-06-corregir-liquidacion')
    await d.getByRole('button', { name: 'Confirmar' }).click()
    await expect(d).toBeHidden()
  })
})
