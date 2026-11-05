/** `globalSetup`: vacía la carpeta de capturas para que solo queden las de esta corrida. */
import { mkdir, rm } from 'node:fs/promises'

import { CAPTURAS_DIR } from './entorno'

export default async function prepararCapturas() {
  await rm(CAPTURAS_DIR, { recursive: true, force: true })
  await mkdir(CAPTURAS_DIR, { recursive: true })
}
