import { execFileSync } from 'node:child_process'

import { expect, iniciarSesion, test } from './apoyo'
import { BACKEND_DIR, ENV_BACKEND, PYTHON } from './entorno'

test.describe.serial('Modelo de Machine Learning', () => {
  test.beforeEach(async ({ page }) => {
    await iniciarSesion(page)
  })

  test('sin modelo en producción, Monitoreo lo indica', async ({ page }) => {
    await page.goto('/monitoreo')
    await expect(page.getByText('Aún no hay un modelo en producción')).toBeVisible()
  })

  test('el modelo inicial se entrena por CLI y aparece en producción', async ({ page }) => {
    // La pantalla no ofrece reentrenar sin un modelo productivo: el primero sale del script.
    const salida = execFileSync(PYTHON, ['scripts/train_model.py', '--algoritmo', 'xgboost', '--promover'], {
      cwd: BACKEND_DIR,
      env: { ...process.env, ...ENV_BACKEND },
      encoding: 'utf-8',
    })
    expect(salida).toMatch(/-> produccion/)
    await page.goto('/monitoreo')
    await expect(page.getByText('Modelo en producción:')).toBeVisible()
    await expect(page.getByRole('listitem').filter({ hasText: '▶ PROD' })).toHaveCount(1)
  })

  test('guarda el umbral de MAPE y persiste tras recargar', async ({ page }) => {
    await page.goto('/monitoreo')
    await page.getByLabel('Umbral MAPE (%)').fill('15')
    await page.getByLabel('Periodos consecutivos').fill('2')
    await page.getByRole('button', { name: 'Guardar umbral' }).click()
    await expect(page.getByText('✔ Guardado')).toBeVisible()
    await page.reload()
    await expect(page.getByLabel('Umbral MAPE (%)')).toHaveValue('15')
    await expect(page.getByLabel('Periodos consecutivos')).toHaveValue('2')
  })

  test('valida que «desde» sea anterior a «hasta» en la ventana de reentrenamiento', async ({ page }) => {
    await page.goto('/monitoreo')
    await page.getByLabel('Ventana de datos: desde').fill('2025-03-31')
    await page.getByLabel('hasta (vacío = hoy)').fill('2025-01-01')
    await expect(page.getByRole('button', { name: '⟳ Reentrenar ahora' })).toBeDisabled()
  })

  test('reentrena desde la pantalla: el Worker ejecuta el job y lo reporta', async ({ page }) => {
    test.setTimeout(180_000)
    await page.goto('/monitoreo')
    await page.getByRole('checkbox', { name: 'RandomForest' }).check()
    await page.getByRole('button', { name: '⟳ Reentrenar ahora' }).click()
    const dialogo = page.getByRole('dialog', { name: 'Confirmar reentrenamiento' })
    await expect(dialogo).toContainText('xgboost, sklearn')
    await dialogo.getByRole('button', { name: 'Reentrenar' }).click()
    await expect(page.getByText(/completado/)).toBeVisible({ timeout: 150_000 })
    // El candidato solo se promueve si mejora el MAPE del productivo; si no, queda descartado.
    await expect(page.getByText(/Último reentrenamiento: \d{4}-\d{2}-\d{2} \(candidato (descartado|promovido)/)).toBeVisible()
    await expect(page.getByRole('listitem').filter({ hasText: '▶ PROD' })).toHaveCount(1)
  })
})
