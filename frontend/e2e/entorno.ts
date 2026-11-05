/**
 * Entorno aislado de las pruebas E2E: BD propia (`ds_e2e`, se recrea en cada corrida), API en
 * 8001 y web en 5174, para no tocar la BD ni los puertos de desarrollo.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const AQUI = path.dirname(fileURLToPath(import.meta.url))
export const FRONTEND_DIR = path.resolve(AQUI, '..')
export const BACKEND_DIR = path.resolve(FRONTEND_DIR, '../backend')
export const TMP_DIR = path.join(AQUI, '.tmp')
export const REPO_DIR = path.resolve(FRONTEND_DIR, '..')

export const API_PORT = Number(process.env.E2E_API_PORT ?? 8001)
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5174)
export const API_URL = `http://localhost:${API_PORT}`
export const WEB_URL = `http://localhost:${WEB_PORT}`

/** Python del venv del backend (Windows o Linux/macOS). */
export const PYTHON = path.join(
  BACKEND_DIR,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)

/** Variables para la API, el Worker y los scripts del backend durante las pruebas. */
export const ENV_BACKEND: Record<string, string> = {
  DATABASE_URL:
    process.env.E2E_DATABASE_URL ?? 'postgresql+psycopg2://ds_user:ds_password@localhost:5432/ds_e2e',
  JWT_SECRET_KEY: 'e2e-secreto-solo-para-pruebas-locales',
  CORS_ORIGINS: WEB_URL,
  ENVIRONMENT: 'e2e',
  ML_ARTIFACTS_DIR: path.join(TMP_DIR, 'ml_artifacts'),
  WORKER_POLL_SEGUNDOS: '2',
  WORKER_EVALUACION_INTERVALO_SEGUNDOS: '3600',
  PYTHONIOENCODING: 'utf-8',
}

export const ADMIN = { email: 'admin@ds.gt', password: 'CambiarAdmin123' }
export const EXCEL_REAL = path.join(REPO_DIR, 'data/raw/VENTAS DIARIAS MARZO 2025.xlsx')
export const EXCEL_SINTETICO = path.join(TMP_DIR, 'historico_sintetico.xlsx')
