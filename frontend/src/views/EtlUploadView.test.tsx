import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EtlUploadView, validarArchivo } from './EtlUploadView'

const api = vi.hoisted(() => ({ subirExcel: vi.fn(), listarLotes: vi.fn() }))
vi.mock('../services/etlApi', async (original) => ({
  ...(await original<typeof import('../services/etlApi')>()),
  subirExcel: api.subirExcel,
  listarLotes: api.listarLotes,
}))

const rechazo = (status: number, data: unknown) =>
  new AxiosError('x', String(status), undefined, undefined, { status, data } as never)

const excel = (nombre = 'ventas.xlsx', tamano = 2048) => new File([new Uint8Array(tamano)], nombre)

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={cliente}>
      <EtlUploadView />
    </QueryClientProvider>,
  )
}
const elegir = (f: File) => fireEvent.change(screen.getByTestId('entrada-archivo'), { target: { files: [f] } })

beforeEach(() => {
  vi.clearAllMocks()
  api.listarLotes.mockResolvedValue({
    total: 2,
    lotes: [
      { id: 'l1', archivo_nombre: 'marzo.xlsx', estado: 'cargado', filas_totales: 103, filas_validas: 100, filas_rechazadas: 3, cargado_por: 'Ana', creado_en: '2026-03-02T15:00:00Z' },
      { id: 'l2', archivo_nombre: 'malo.xlsx', estado: 'rechazado', filas_totales: 12, filas_validas: 0, filas_rechazadas: 12, cargado_por: 'Luis', creado_en: '2026-03-01T15:00:00Z' },
    ],
  })
})

describe('validarArchivo', () => {
  it('acepta .xlsx dentro del límite', () => expect(validarArchivo({ name: 'A.XLSX', size: 10 })).toBeNull())
  it('rechaza otras extensiones, vacíos y más de 20 MB', () => {
    expect(validarArchivo({ name: 'a.csv', size: 10 })).toMatch(/xlsx/)
    expect(validarArchivo({ name: 'a.xlsx', size: 0 })).toMatch(/vacío/)
    expect(validarArchivo({ name: 'a.xlsx', size: 21 * 1024 * 1024 })).toMatch(/20 MB/)
  })
})

describe('<EtlUploadView />', () => {
  it('muestra el historial de lotes con válidas, rechazadas y estado', async () => {
    montar()
    const fila = (await screen.findByText('marzo.xlsx')).closest('tr')!
    expect(fila).toHaveTextContent('Ana')
    expect(fila).toHaveTextContent('100')
    expect(fila).toHaveTextContent('cargado')
    expect((await screen.findByText('malo.xlsx')).closest('tr')).toHaveTextContent('rechazado')
  })

  it('archivo inválido no se envía y avisa el motivo', async () => {
    montar()
    elegir(excel('datos.csv'))
    expect(await screen.findByText('Solo se admiten archivos Excel (.xlsx).')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cargar archivo' })).toBeDisabled()
  })

  it('carga correcta: envía modo y archivo, muestra resumen y advertencias, y refresca el historial', async () => {
    api.subirExcel.mockImplementation(async (_f: File, _o: unknown, alProgreso: (n: number) => void) => {
      alProgreso(100)
      return { lote_id: 'l9', estado: 'cargado', filas_totales: 50, filas_validas: 48, filas_rechazadas: 2, advertencias: ['Vendedor sin usuario: Pedro'], rango_fechas: { desde: '2026-03-01', hasta: '2026-03-31' } }
    })
    montar()
    await screen.findByText('marzo.xlsx')
    elegir(excel())
    fireEvent.change(screen.getByLabelText('Modo de carga'), { target: { value: 'parcial' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cargar archivo' }))

    expect(await screen.findByText(/48 filas válidas de 50/)).toBeInTheDocument()
    expect(screen.getByText('Vendedor sin usuario: Pedro')).toBeInTheDocument()
    expect(api.subirExcel.mock.calls[0][0].name).toBe('ventas.xlsx')
    expect(api.subirExcel.mock.calls[0][1]).toMatchObject({ modo: 'parcial' })
    await waitFor(() => expect(api.listarLotes.mock.calls.length).toBeGreaterThan(1))
  })

  it('lote duplicado (400) se explica sin mostrar tabla de errores', async () => {
    api.subirExcel.mockRejectedValue(rechazo(400, { codigo: 'LOTE_DUPLICADO', mensaje: 'El archivo ya fue cargado el 2026-03-02.' }))
    montar()
    elegir(excel())
    fireEvent.click(screen.getByRole('button', { name: 'Cargar archivo' }))
    expect(await screen.findByText(/Lote duplicado/)).toBeInTheDocument()
    expect(screen.getByText(/ya fue cargado el 2026-03-02/)).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: /errores de validación/i })).toBeNull()
  })

  it('rechazo de esquema (422) muestra el desglose por fila y columna', async () => {
    api.subirExcel.mockRejectedValue(
      rechazo(422, {
        codigo: 'DATOS_INVALIDOS',
        lote_id: 'l7',
        total_errores: 3,
        errores: [
          { fila: 5, columna: 'cantidad', valor: '-2', mensaje: 'La cantidad no puede ser negativa.' },
          { fila: 9, columna: 'fecha', valor: 'ayer', mensaje: 'Fecha inválida.' },
        ],
      }),
    )
    montar()
    elegir(excel())
    fireEvent.click(screen.getByRole('button', { name: 'Cargar archivo' }))

    expect(await screen.findByText(/3 errores detectados/)).toBeInTheDocument()
    const tabla = screen.getByRole('table', { name: /errores de validación/i })
    expect(tabla).toHaveTextContent('cantidad')
    expect(tabla).toHaveTextContent('La cantidad no puede ser negativa.')
    expect(tabla).toHaveTextContent('Fecha inválida.')
    expect(screen.getByText(/primeros 2 de 3 errores/)).toBeInTheDocument()
  })

  it('otros errores del servidor (403) se muestran como alerta genérica', async () => {
    api.subirExcel.mockRejectedValue(rechazo(403, { codigo: 'PERMISO_DENEGADO', mensaje: 'Sin permiso para cargar.' }))
    montar()
    elegir(excel())
    fireEvent.click(screen.getByRole('button', { name: 'Cargar archivo' }))
    expect(await screen.findByText('Sin permiso para cargar.')).toBeInTheDocument()
  })
})
