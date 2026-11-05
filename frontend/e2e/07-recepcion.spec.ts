import type { Page } from '@playwright/test'

import { capturar, expect, iniciarSesion, test, toast } from './apoyo'

/** Mercadería que recibe la planta central; da existencias para el plan de carga (08). */
export const RECIBIDO = [
  { sku: '500179', cantidad: '300', precio: '61' },
  { sku: '599033', cantidad: '150', precio: '50' },
]

async function agregarProducto(page: Page, sku: string, cantidad: string, precio: string) {
  await page.getByRole('combobox', { name: 'Código del producto' }).fill(sku)
  await page.keyboard.press('Enter')
  await page.getByRole('spinbutton', { name: new RegExp(`^Cantidad recibida de ${sku}`) }).fill(cantidad)
  await page.getByRole('textbox', { name: new RegExp(`^Precio unitario de ${sku}`) }).fill(precio)
}

async function encabezadoFel(page: Page, numero: string) {
  await page.getByLabel('Serie FEL').fill('e2ea')
  await page.getByLabel('Número FEL').fill(numero)
  await page.getByLabel('Fecha de emisión').fill('2025-03-31')
}

test.describe.serial('Recepción de mercadería con factura FEL', () => {
  test.beforeEach(async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/recepcion')
  })

  test('sin productos no se puede guardar', async ({ page }) => {
    await encabezadoFel(page, '000123')
    await expect(page.getByRole('button', { name: 'Guardar recepción' })).toBeDisabled()
  })

  test('registra una recepción sin pedido y sube el stock', async ({ page }) => {
    await encabezadoFel(page, '000123')
    for (const p of RECIBIDO) await agregarProducto(page, p.sku, p.cantidad, p.precio)
    await expect(page.getByRole('row', { name: /^Total/ })).toContainText('Q 25,800.00')
    await capturar(page, '07-01-recepcion-factura-fel')
    await page.getByRole('button', { name: 'Guardar recepción' }).click()
    await expect(toast(page, /recepción|registrad|guardad/i)).toBeVisible()

    await page.goto('/inventario')
    const fila = page.getByRole('row', { name: /BIG COLA PET NO RETORNABLE 3030 ML 6/ }).first()
    await expect(fila).toContainText('300')
    await capturar(page, '07-02-inventario-tras-recepcion')
  })

  test('la misma factura (serie + número) no se acepta dos veces', async ({ page }) => {
    await encabezadoFel(page, '000123')
    await agregarProducto(page, '500179', '10', '61')
    await page.getByRole('button', { name: 'Guardar recepción' }).click()
    await expect(toast(page, /factura/i)).toBeVisible()
    await capturar(page, '07-03-factura-duplicada')
    // Lo capturado se conserva para corregir el número.
    await expect(page.getByLabel('Número FEL')).toHaveValue('000123')
  })
})
