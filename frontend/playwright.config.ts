import { defineConfig, devices } from '@playwright/test'

import { API_URL, WEB_PORT, WEB_URL } from './e2e/entorno'

/**
 * Pruebas E2E del sistema completo (PostgreSQL + API + Worker + SPA).
 *
 *   cd frontend && npm run test:e2e
 *
 * Requisitos: PostgreSQL 16 en localhost:5432 con el usuario `ds_user` (puede ser el contenedor
 * `postgres` de infra/docker-compose.yml) y `backend/.venv` instalado (`make install`).
 * La BD `ds_e2e` se BORRA y recrea en cada corrida; nunca se usa la BD de desarrollo.
 *
 * Los archivos corren en orden y en un solo worker: cada uno parte del estado que dejó el anterior
 * (catálogos → ETL → modelo → recepción → plan de carga → liquidación → reportes), igual que el
 * flujo real del negocio.
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/preparar-capturas.ts',
  outputDir: './e2e/.tmp/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { outputFolder: 'e2e/.tmp/report', open: 'never' }]],
  use: {
    baseURL: WEB_URL,
    actionTimeout: 15_000,
    locale: 'es-GT',
    timezoneId: 'America/Guatemala',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // deviceScaleFactor 2: capturas nítidas para documentos (e2e/capturas).
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 },
    },
  ],
  // La API (y el Worker) esperan a que el lanzador recree la BD; la web solo necesita el proxy.
  webServer: [
    {
      command: 'node --experimental-strip-types --no-warnings e2e/servidor-backend.ts',
      url: `${API_URL}/health`,
      timeout: 240_000,
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      env: { VITE_PROXY_TARGET: API_URL },
      url: WEB_URL,
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
})
