import { expect, iniciarSesion, test, toast } from './apoyo'

const SKU = 'E2E-001'

test.describe.serial('Productos e inventario (kardex)', () => {
  test.beforeEach(async ({ page }) => {
    await iniciarSesion(page)
    await page.goto('/productos')
  })

  test('crea un producto; el SKU se normaliza a mayúsculas', async ({ page }) => {
    await page.getByRole('button', { name: '+ Nuevo producto' }).click()
    const d = page.getByRole('dialog', { name: 'Nuevo producto' })
    await d.getByLabel('SKU').fill('e2e-001')
    await d.getByLabel('Nombre').fill('Bebida de prueba E2E 600 ml')
    await d.getByLabel('Categoría').selectOption({ label: 'Big' })
    await d.getByLabel('Precio de venta').fill('12.50')
    await d.getByLabel('Costo unitario').fill('8')
    await d.getByLabel('Stock mínimo').fill('20')
    await d.getByLabel('Unidades por paquete').fill('6')
    await d.getByLabel('Medida (ml, opcional)').fill('600')
    await d.getByLabel('Sabor (opcional)').fill('Cola')
    await d.getByRole('button', { name: 'Crear producto' }).click()
    await expect(d).toBeHidden()
    await page.getByPlaceholder('SKU o nombre').fill('E2E')
    const fila = page.getByRole('row', { name: new RegExp(SKU) })
    await expect(fila).toContainText('Bebida de prueba E2E 600 ml')
    await expect(fila).toContainText('6 × 600 ml')
  })

  test('rechaza un SKU duplicado sin distinguir mayúsculas', async ({ page }) => {
    await page.getByRole('button', { name: '+ Nuevo producto' }).click()
    const d = page.getByRole('dialog', { name: 'Nuevo producto' })
    await d.getByLabel('SKU').fill('E2E-001')
    await d.getByLabel('Nombre').fill('Duplicado')
    await d.getByLabel('Categoría').selectOption({ label: 'Big' })
    await d.getByRole('button', { name: 'Crear producto' }).click()
    await expect(toast(page, /SKU/i)).toBeVisible()
    await expect(d).toBeVisible()
  })

  test('edita el precio de un producto', async ({ page }) => {
    await page.getByPlaceholder('SKU o nombre').fill(SKU)
    await page.getByRole('button', { name: `Editar ${SKU}` }).click()
    const d = page.getByRole('dialog')
    await d.getByLabel('Precio de venta').fill('13.75')
    await d.getByRole('button', { name: 'Guardar cambios' }).click()
    await expect(d).toBeHidden()
    await expect(page.getByRole('row', { name: new RegExp(SKU) })).toContainText('13.75')
  })

  test('ajusta stock: incremento, decremento inválido y conteo físico', async ({ page }) => {
    await page.getByPlaceholder('SKU o nombre').fill(SKU)
    await page.getByRole('button', { name: `Ajustar stock de ${SKU}` }).click()
    let d = page.getByRole('dialog', { name: `Ajustar stock · ${SKU}` })
    await d.getByLabel('Cantidad').fill('50')
    await d.getByLabel('Motivo').fill('Ingreso inicial E2E')
    await expect(d.getByText('Stock resultante:')).toContainText('50')
    await d.getByRole('button', { name: 'Aplicar ajuste' }).click()
    await expect(d).toBeHidden()

    // No se puede restar más de lo que hay.
    await page.getByRole('button', { name: `Ajustar stock de ${SKU}` }).click()
    d = page.getByRole('dialog', { name: `Ajustar stock · ${SKU}` })
    await d.getByLabel('Tipo de ajuste').selectOption({ label: 'Decremento (restar)' })
    await d.getByLabel('Cantidad').fill('80')
    await d.getByLabel('Motivo').fill('Merma excesiva E2E')
    await d.getByRole('button', { name: 'Aplicar ajuste' }).click()
    await expect(d.getByText('El stock no puede quedar por debajo de lo reservado (0).')).toBeVisible()
    await expect(d).toBeVisible()

    await d.getByLabel('Tipo de ajuste').selectOption({ label: 'Fijar (conteo físico)' })
    await d.getByLabel('Stock físico contado').fill('45')
    await d.getByLabel('Motivo').fill('Conteo físico E2E')
    await d.getByRole('button', { name: 'Aplicar ajuste' }).click()
    await expect(d).toBeHidden()
    await expect(page.getByRole('row', { name: new RegExp(SKU) })).toContainText('45')
  })

  test('el kardex registra los ajustes con su motivo', async ({ page }) => {
    await page.goto('/inventario')
    const filtro = page.getByLabel('Producto')
    const valor = await filtro.locator('option', { hasText: SKU }).getAttribute('value')
    await filtro.selectOption(valor!)
    await expect(page.getByText('Ingreso inicial E2E')).toBeVisible()
    await expect(page.getByText('Conteo físico E2E')).toBeVisible()
  })

  test('da de baja y reactiva un producto', async ({ page }) => {
    await page.getByPlaceholder('SKU o nombre').fill(SKU)
    await page.getByRole('button', { name: `Dar de baja ${SKU}` }).click()
    await page.getByRole('dialog', { name: 'Dar de baja producto' }).getByRole('button', { name: 'Dar de baja' }).click()
    await expect(page.getByRole('row', { name: new RegExp(SKU) })).toHaveCount(0)
    await page.getByLabel('Estado').selectOption({ label: 'Dados de baja' })
    await page.getByRole('button', { name: `Reactivar ${SKU}` }).click()
    await expect(page.getByRole('button', { name: `Reactivar ${SKU}` })).toHaveCount(0)
    await page.getByLabel('Estado').selectOption({ label: 'Activos' })
    await expect(page.getByRole('row', { name: new RegExp(SKU) })).toBeVisible()
  })
})
