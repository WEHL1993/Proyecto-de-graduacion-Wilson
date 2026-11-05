import type { Page } from '@playwright/test'

import { capturar, expect, FECHA_OPERACION, iniciarSesion, test, toast } from './apoyo'

async function consultar(page: Page, ruta: string) {
  await page.goto('/')
  const selector = page.getByLabel('Ruta')
  // El select es usable antes de que la vista fije su ruta por defecto; elegir antes la pisaría.
  await expect(selector).not.toHaveValue('')
  await selector.selectOption({ label: ruta })
  await expect(selector.locator('option:checked')).toHaveText(ruta)
  await page.getByLabel('Fecha operación').fill(FECHA_OPERACION)
  await page.getByRole('button', { name: 'Consultar' }).click()
}

test.describe.serial('Plan de carga: predicción, aprobación y rechazo', () => {
  test.beforeEach(async ({ page }) => iniciarSesion(page))

  test('genera el plan sugerido con la demanda del modelo y el stock disponible', async ({ page }) => {
    await consultar(page, 'ANTONIO Antonio')
    await expect(page.getByText(/Modelo activo: \w+ v[\d.]+/)).toBeVisible()
    await capturar(page, '08-00-dashboard-sin-plan')
    await page.getByRole('button', { name: 'Generar plan sugerido' }).click()
    await expect(page.getByRole('heading', { name: `Plan de carga sugerido · ${FECHA_OPERACION}` })).toBeVisible()
    await expect(page.getByText('borrador', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'KPIs' })).toBeVisible()
    await capturar(page, '08-01-plan-de-carga-generado')

    // Regla ADR-07: sugerido = mín(demanda, stock). 598896 no tiene existencias → sugerido 0.
    const sinStock = page.getByRole('row', { name: /^Incluir 598896/ })
    await expect(sinStock.getByRole('checkbox')).not.toBeChecked()
    await expect(sinStock.getByRole('spinbutton')).toHaveValue('0')
    // 500179 tiene 300 en stock (recepción) → se sugiere y queda marcado.
    const conStock = page.getByRole('row', { name: /^Incluir 500179/ })
    await expect(conStock.getByRole('checkbox')).toBeChecked()
    await expect(conStock.getByRole('cell').nth(4)).toHaveText('300')
  })

  test('no deja aprobar una cantidad mayor que el stock disponible', async ({ page }) => {
    await consultar(page, 'ANTONIO Antonio')
    const cantidad = page.getByRole('spinbutton', { name: 'Cantidad aprobada de 500179' })
    await cantidad.fill('301')
    await expect(page.getByRole('button', { name: '✔ Aprobar' })).toBeDisabled()
    await cantidad.fill('25')
    await expect(page.getByRole('button', { name: '✔ Aprobar' })).toBeEnabled()
  })

  test('envía a aprobación y aprueba; el stock aprobado queda reservado', async ({ page }) => {
    await consultar(page, 'ANTONIO Antonio')
    await page.getByRole('button', { name: 'Enviar a aprobación' }).click()
    await expect(toast(page, 'Plan enviado a aprobación.')).toBeVisible()
    await expect(page.getByText('pendiente aprobacion').or(page.getByText('pendiente_aprobacion'))).toBeVisible()

    await page.getByRole('spinbutton', { name: 'Cantidad aprobada de 500179' }).fill('25')
    await page.getByRole('button', { name: '✔ Aprobar' }).click()
    await expect(page.getByText('aprobada', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '↩ Revertir aprobación' })).toBeVisible()
    await page.getByRole('heading', { name: `Plan de carga sugerido · ${FECHA_OPERACION}` }).scrollIntoViewIfNeeded()
    await page.mouse.wheel(0, -300) // deja visibles el encabezado, el estado y las primeras filas
    await capturar(page, '08-02-plan-de-carga-aprobado')

    await page.goto('/inventario')
    const fila = page.getByRole('row', { name: /BIG COLA PET NO RETORNABLE 3030 ML 6/ }).first()
    await expect(fila.getByRole('cell').nth(2)).toHaveText('25') // reservado
    await expect(fila.getByRole('cell').nth(3)).toHaveText('275') // disponible
    await capturar(page, '08-03-stock-reservado')
  })

  test('rechazar un plan exige motivo', async ({ page }) => {
    await consultar(page, 'CORNELIO Cornelio')
    await page.getByRole('button', { name: 'Generar plan sugerido' }).click()
    await page.getByRole('button', { name: 'Rechazar' }).click()
    const d = page.getByRole('dialog', { name: 'Rechazar plan de carga' })
    await expect(d.getByRole('button', { name: 'Rechazar plan' })).toBeDisabled()
    await d.getByLabel('Motivo del rechazo (obligatorio)').fill('Camión en mantenimiento')
    await capturar(page, '08-04-rechazo-con-motivo')
    await d.getByRole('button', { name: 'Rechazar plan' }).click()
    await expect(d).toBeHidden()
    // Un plan rechazado deja de estar vigente: se puede generar uno nuevo para esa ruta y fecha.
    await expect(page.getByText('No hay plan de carga vigente para esta ruta y fecha')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Generar plan sugerido' })).toBeVisible()
  })

  test('el plan muestra el pronóstico de demanda por producto en un gráfico', async ({ page }) => {
    await consultar(page, 'CESAR Cesar')
    await page.getByRole('button', { name: 'Generar plan sugerido' }).click()
    await expect(page.getByRole('heading', { name: 'Demanda predicha' })).toBeVisible()
    await page.getByLabel('Producto del gráfico').selectOption({ label: '500179 · BIG COLA PET NO RETORNABLE 3030 ML 6' })
    await page.getByRole('heading', { name: 'Demanda predicha' }).scrollIntoViewIfNeeded()
    await capturar(page, '08-05-grafico-de-demanda-predicha')
    await expect(page.locator('.recharts-surface').first()).toBeVisible()
  })
})
