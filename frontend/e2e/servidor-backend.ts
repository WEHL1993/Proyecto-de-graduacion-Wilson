/**
 * Lanzador del backend para Playwright (`webServer`), multiplataforma:
 * 1) recrea la BD `ds_e2e` (scripts/e2e_preparar_bd.py), 2) levanta el Worker y la API.
 * Al terminar Playwright (SIGTERM/SIGINT) detiene ambos procesos.
 */
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'

import { API_PORT, BACKEND_DIR, ENV_BACKEND, PYTHON } from './entorno.ts'

const env = { ...process.env, ...ENV_BACKEND }
const opciones = { cwd: BACKEND_DIR, env, stdio: 'inherit' as const }

const prep = spawnSync(PYTHON, ['scripts/e2e_preparar_bd.py'], opciones)
if (prep.status !== 0) process.exit(prep.status ?? 1)

const hijos: ChildProcess[] = [
  spawn(PYTHON, ['-m', 'app.workers.main'], opciones),
  spawn(PYTHON, ['-m', 'uvicorn', 'app.main:app', '--port', String(API_PORT)], opciones),
]

const detener = () => {
  for (const h of hijos) h.kill()
  process.exit(0)
}
process.on('SIGTERM', detener)
process.on('SIGINT', detener)
for (const h of hijos) h.on('exit', (code) => code && process.exit(code))
