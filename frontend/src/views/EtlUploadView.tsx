import { useRef, useState } from 'react'
import type { DragEvent, KeyboardEvent } from 'react'
import { Button } from '../components/common/Button'
import { Campo, CLASE_INPUT, Card } from '../components/common/Card'
import { AlertBanner, Cargando, EmptyState } from '../components/feedback/feedback'
import { TAMANO_PAGINA_LOTES, useEtlConfig, useLotes, useSubirExcel } from '../hooks/useEtl'
import { errorDeValidacion } from '../services/etlApi'
import type { ModoCarga } from '../services/etlApi'
import type { EtlValidationError, LoteItem } from '../types'
import { apiError, mensajeError } from '../utils/errors'
import { fmtInt } from '../utils/format'

export const TAMANO_MAXIMO_MB = 20

/** Motivo por el que un archivo no se envía, o `null` si es válido (`.xlsx` de hasta 20 MB). */
export function validarArchivo(archivo: { name: string; size: number }): string | null {
  if (!archivo.name.toLowerCase().endsWith('.xlsx')) return 'Solo se admiten archivos Excel (.xlsx).'
  if (archivo.size === 0) return 'El archivo está vacío.'
  if (archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024) return `El archivo supera el máximo de ${TAMANO_MAXIMO_MB} MB.`
  return null
}

const ESTILO_ESTADO: Record<string, string> = {
  cargado: 'bg-good/10 text-good',
  rechazado: 'bg-bad/10 text-bad',
  validado: 'bg-brand/10 text-brand',
  recibido: 'bg-surface text-muted',
}

export function EstadoLote({ estado }: { estado: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${ESTILO_ESTADO[estado] ?? 'bg-surface text-muted'}`}>
      {estado}
    </span>
  )
}

// ---------------------------------------------------------------- dropzone
function Dropzone({ archivo, deshabilitado, onElegir }: { archivo: File | null; deshabilitado: boolean; onElegir: (f: File) => void }) {
  const entrada = useRef<HTMLInputElement>(null)
  const [encima, setEncima] = useState(false)

  const soltar = (e: DragEvent) => {
    e.preventDefault()
    setEncima(false)
    const f = e.dataTransfer.files[0]
    if (f && !deshabilitado) onElegir(f)
  }
  const abrir = () => !deshabilitado && entrada.current?.click()
  const alTeclear = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      abrir()
    }
  }

  return (
    <div
      role="button"
      tabIndex={deshabilitado ? -1 : 0}
      aria-disabled={deshabilitado}
      aria-label="Zona de carga: arrastre un archivo .xlsx o presione Enter para elegirlo"
      onClick={abrir}
      onKeyDown={alTeclear}
      onDragOver={(e) => {
        e.preventDefault()
        if (!deshabilitado) setEncima(true)
      }}
      onDragLeave={() => setEncima(false)}
      onDrop={soltar}
      className={`flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed px-6 py-10 text-center transition ${
        encima ? 'border-brand bg-brand/5' : 'border-line hover:bg-surface'
      } ${deshabilitado ? 'cursor-not-allowed opacity-60' : ''}`}
    >
      <span aria-hidden className="text-2xl">
        📄
      </span>
      {archivo ? (
        <>
          <p className="font-medium">{archivo.name}</p>
          <p className="num text-xs text-muted">{(archivo.size / 1024).toFixed(1)} KB · clic para cambiar</p>
        </>
      ) : (
        <>
          <p className="font-medium">Arrastre aquí el Excel de ventas (.xlsx)</p>
          <p className="text-xs text-muted">o haga clic para seleccionarlo · máximo {TAMANO_MAXIMO_MB} MB</p>
        </>
      )}
      <input
        ref={entrada}
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="sr-only"
        tabIndex={-1}
        aria-label="Archivo Excel"
        data-testid="entrada-archivo"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onElegir(f)
          e.target.value = ''
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------- resultado de validación
const LIMITE_FILAS_VISIBLES = 200

export function ErroresValidacion({ error }: { error: EtlValidationError }) {
  const visibles = error.errores.slice(0, LIMITE_FILAS_VISIBLES)
  const multihoja = error.errores.some((e) => e.hoja)
  return (
    <div className="flex flex-col gap-2">
      <AlertBanner>
        <strong>Lote rechazado ({error.codigo}).</strong> El archivo no cumple las validaciones: {fmtInt(error.total_errores)}{' '}
        {error.total_errores === 1 ? 'error' : 'errores'} detectados. Corrija el Excel y vuelva a cargarlo.
      </AlertBanner>
      <div className="max-h-80 overflow-auto rounded-md border border-line">
        <table className="w-full text-sm">
          <caption className="sr-only">Errores de validación por fila y columna</caption>
          <thead className="sticky top-0 bg-panel">
            <tr className="text-left text-xs text-muted">
              {multihoja && <th className="px-2 py-1.5">Hoja</th>}
              <th className="px-2 py-1.5">Fila</th>
              <th className="px-2 py-1.5">Columna</th>
              <th className="px-2 py-1.5">Valor</th>
              <th className="px-2 py-1.5">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((e, i) => (
              <tr key={i} className="border-t border-line align-top">
                {multihoja && <td className="px-2 py-1.5">{e.hoja ?? '—'}</td>}
                <td className="num px-2 py-1.5">{e.fila}</td>
                <td className="px-2 py-1.5 font-medium">{e.columna}</td>
                <td className="px-2 py-1.5 text-muted">{e.valor ?? '—'}</td>
                <td className="px-2 py-1.5">{e.mensaje}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error.total_errores > visibles.length && (
        <p className="text-xs text-muted">
          Se muestran los primeros {fmtInt(visibles.length)} de {fmtInt(error.total_errores)} errores.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- historial
function Historial() {
  const [pagina, setPagina] = useState(0)
  const lotes = useLotes(pagina)
  const total = lotes.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / TAMANO_PAGINA_LOTES))

  return (
    <Card titulo="Historial de lotes procesados">
      {lotes.isLoading && <Cargando texto="Cargando historial…" />}
      {lotes.isError && <AlertBanner>{mensajeError(lotes.error)}</AlertBanner>}
      {lotes.data && !lotes.data.lotes.length && (
        <EmptyState titulo="Aún no hay cargas" detalle="Los lotes procesados aparecerán aquí con su resultado de validación." />
      )}
      {!!lotes.data?.lotes.length && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Lotes ETL</caption>
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="py-2 pr-3">Fecha</th>
                  <th className="py-2 pr-3">Archivo</th>
                  <th className="py-2 pr-3">Cargado por</th>
                  <th className="py-2 pr-3 text-right">Filas válidas</th>
                  <th className="py-2 pr-3 text-right">Rechazadas</th>
                  <th className="py-2">Estado</th>
                </tr>
              </thead>
              <tbody>
                {lotes.data.lotes.map((l: LoteItem) => (
                  <tr key={l.id} className="border-t border-line">
                    <td className="num whitespace-nowrap py-2 pr-3">{new Date(l.creado_en).toLocaleString('es-GT', { dateStyle: 'short', timeStyle: 'short' })}</td>
                    <td className="py-2 pr-3 break-all">{l.archivo_nombre}</td>
                    <td className="py-2 pr-3">{l.cargado_por}</td>
                    <td className="num py-2 pr-3 text-right">{fmtInt(l.filas_validas)}</td>
                    <td className={`num py-2 pr-3 text-right ${l.filas_rechazadas ? 'font-semibold text-bad' : ''}`}>{fmtInt(l.filas_rechazadas)}</td>
                    <td className="py-2">
                      <EstadoLote estado={l.estado} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-muted">
            <span>
              Página {pagina + 1} de {paginas} · {fmtInt(total)} lotes
            </span>
            <span className="flex gap-2">
              <Button disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </Button>
              <Button disabled={pagina + 1 >= paginas} onClick={() => setPagina((p) => p + 1)}>
                Siguiente
              </Button>
            </span>
          </div>
        </>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------- vista
export function EtlUploadView() {
  const [archivo, setArchivo] = useState<File | null>(null)
  const [problema, setProblema] = useState<string | null>(null)
  const [modo, setModo] = useState<ModoCarga>('estricto')
  const [hoja, setHoja] = useState('')
  const [periodo, setPeriodo] = useState('')
  const subida = useSubirExcel()
  // ADR-14: con el arranque cerrado las ventas nuevas entran solo por la liquidación diaria.
  const bloqueado = useEtlConfig().data?.carga_excel_habilitada === false

  const elegir = (f: File) => {
    subida.reset()
    const motivo = validarArchivo(f)
    setProblema(motivo)
    setArchivo(motivo ? null : f)
  }
  const enviar = () => archivo && subida.mutate({ archivo, opciones: { modo, hoja: hoja.trim() || undefined, periodo: periodo || undefined } })

  const validacion = subida.isError ? errorDeValidacion(subida.error) : null
  const api = subida.isError ? apiError(subida.error) : null
  const duplicado = api?.codigo === 'LOTE_DUPLICADO'
  // Bytes ya enviados; el resto es validación en el servidor (la respuesta llega al terminar).
  const validando = subida.isPending && subida.progreso >= 100

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-lg font-semibold">Carga de datos históricos (ETL)</h1>
        <p className="text-sm text-muted">
          Suba el Excel de ventas. Se valida estructura, tipos y reglas de negocio antes de cargarlo; los archivos ya cargados se rechazan.
        </p>
      </header>

      {bloqueado && (
        <AlertBanner tipo="info">
          <strong>Carga de Excel deshabilitada.</strong> El arranque está cerrado: las ventas nuevas se registran en la
          liquidación diaria.
        </AlertBanner>
      )}

      <Card titulo="Nuevo archivo">
        <div className="flex flex-col gap-4">
          <Dropzone archivo={archivo} deshabilitado={subida.isPending || bloqueado} onElegir={elegir} />
          {problema && <AlertBanner>{problema}</AlertBanner>}

          <div className="flex flex-wrap items-end gap-3">
            <Campo etiqueta="Modo de carga">
              <select value={modo} onChange={(e) => setModo(e.target.value as ModoCarga)} disabled={subida.isPending} className={CLASE_INPUT}>
                <option value="estricto">Estricto: rechaza todo el lote ante un error</option>
                <option value="parcial">Parcial: carga las filas válidas</option>
              </select>
            </Campo>
            <Campo etiqueta="Hoja (opcional)">
              <input value={hoja} onChange={(e) => setHoja(e.target.value)} disabled={subida.isPending} placeholder="Primera hoja" className={`${CLASE_INPUT} w-40`} />
            </Campo>
            <Campo etiqueta="Periodo (opcional)">
              <input type="month" value={periodo} onChange={(e) => setPeriodo(e.target.value)} disabled={subida.isPending} className={CLASE_INPUT} />
            </Campo>
            <Button variant="primary" disabled={!archivo || subida.isPending || bloqueado} onClick={enviar}>
              {subida.isPending ? 'Procesando…' : 'Cargar archivo'}
            </Button>
          </div>

          {subida.isPending && (
            <div>
              <div className="mb-1 flex justify-between text-xs text-muted">
                <span>{validando ? 'Validando en el servidor…' : 'Enviando archivo…'}</span>
                <span className="num">{subida.progreso} %</span>
              </div>
              <div
                role="progressbar"
                aria-label="Progreso de carga"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={subida.progreso}
                className="h-2 overflow-hidden rounded-full bg-line"
              >
                <div className={`h-full bg-brand transition-all ${validando ? 'animate-pulse' : ''}`} style={{ width: `${subida.progreso}%` }} />
              </div>
            </div>
          )}

          {subida.isSuccess && (
            <div className="flex flex-col gap-2">
              <AlertBanner tipo="exito">
                <strong>Lote {subida.data.estado}.</strong> {fmtInt(subida.data.filas_validas)} filas válidas de {fmtInt(subida.data.filas_totales)}
                {subida.data.filas_rechazadas > 0 && `; ${fmtInt(subida.data.filas_rechazadas)} rechazadas`}
                {subida.data.rango_fechas && ` · ${subida.data.rango_fechas.desde} → ${subida.data.rango_fechas.hasta}`}.
              </AlertBanner>
              {!!subida.data.advertencias?.length && (
                <ul className="list-disc rounded-md border border-warn bg-panel py-2 pl-7 pr-3 text-sm">
                  {subida.data.advertencias.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {duplicado && (
            <AlertBanner tipo="info">
              <strong>Lote duplicado.</strong> {api?.mensaje ?? 'Este archivo ya fue cargado anteriormente.'} Revise el historial inferior.
            </AlertBanner>
          )}
          {validacion && <ErroresValidacion error={validacion} />}
          {subida.isError && !duplicado && !validacion && <AlertBanner>{mensajeError(subida.error)}</AlertBanner>}
        </div>
      </Card>

      <Historial />
    </div>
  )
}
