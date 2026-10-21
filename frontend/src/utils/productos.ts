/** Pasa el contenido en ml al inicio del nombre («BIG COLA PET 250 ML 24» → «250 ML BIG COLA PET 24»). */
export function nombreConMlAlInicio(nombre: string): string {
  const m = /(\d+(?:[.,]\d+)?)\s*ml\b/i.exec(nombre)
  if (!m) return nombre
  const resto = `${nombre.slice(0, m.index)} ${nombre.slice(m.index + m[0].length)}`.replace(/\s+/g, ' ').trim()
  return `${m[1]} ML ${resto}`
}

const normalizar = (s: string) => s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()

/**
 * Búsqueda de producto por SKU o nombre (con los ml al inicio), sin mayúsculas ni tildes.
 * Cada término debe empezar una palabra: «250» no trae «2250 ML».
 */
export function coincideBusqueda(sku: string, nombre: string, busqueda: string): boolean {
  const terminos = normalizar(busqueda).split(/\s+/).filter(Boolean)
  if (!terminos.length) return true
  const palabras = normalizar(`${sku} ${nombreConMlAlInicio(nombre)}`).split(/\s+/)
  return terminos.every((t) => palabras.some((p) => p.startsWith(t)))
}
