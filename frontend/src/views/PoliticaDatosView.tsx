import { useEffect, useState } from 'react'
import { Button } from '../components/common/Button'
import { CLASE_INPUT, Campo, Card } from '../components/common/Card'
import { Modal } from '../components/common/Modal'
import { AlertBanner, Cargando } from '../components/feedback/feedback'
import { useEtlConfig, useGuardarEtlConfig } from '../hooks/useEtl'
import { useConfigLiquidacion, useGuardarConfigLiquidacion } from '../hooks/useLiquidaciones'
import type { EtlConfig } from '../types'
import { mensajeError } from '../utils/errors'

type Fuente = EtlConfig['fuente_reentrenamiento']
const FUENTES: { valor: Fuente; etiqueta: string }[] = [
  { valor: 'excel_mas_liquidacion', etiqueta: 'Base Excel + liquidaciones (recomendada)' },
  { valor: 'liquidacion', etiqueta: 'Solo liquidaciones (≥ 28 días por ruta)' },
  { valor: 'excel_historico', etiqueta: 'Solo Excel histórico' },
]

/** Panel mínimo del Administrador: cierre del arranque ETL, fuente de reentrenamiento y umbral de caja. */
export function PoliticaDatosView() {
  const etl = useEtlConfig()
  const guardarEtl = useGuardarEtlConfig()
  const caja = useConfigLiquidacion()
  const guardarCaja = useGuardarConfigLiquidacion()
  const [fuente, setFuente] = useState<Fuente>('excel_mas_liquidacion')
  const [umbral, setUmbral] = useState('')
  const [confirmar, setConfirmar] = useState(false)

  useEffect(() => {
    if (etl.data) setFuente(etl.data.fuente_reentrenamiento)
  }, [etl.data])
  useEffect(() => {
    if (caja.data) setUmbral(String(Number(caja.data.umbral_diferencia_caja)))
  }, [caja.data])

  if (etl.isLoading) return <Cargando />
  const habilitada = etl.data?.carga_excel_habilitada ?? true
  const umbralValido = umbral.trim() !== '' && Number(umbral) >= 0 && Number.isFinite(Number(umbral))

  const fijarArranque = (carga_excel_habilitada: boolean) =>
    guardarEtl.mutate({ carga_excel_habilitada, fuente_reentrenamiento: fuente }, { onSuccess: () => setConfirmar(false) })

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-lg font-semibold">Política de datos del modelo</h1>
        <p className="text-sm text-muted">
          El entrenamiento inicial usa los Excel de la empresa. Después, las ventas nuevas entran solo por la liquidación diaria.
        </p>
      </header>
      {(etl.isError || guardarEtl.isError) && <AlertBanner>{mensajeError(etl.error ?? guardarEtl.error)}</AlertBanner>}

      <Card titulo="Arranque del ETL">
        <p className="text-sm">
          Carga de Excel:{' '}
          <strong className={habilitada ? 'text-good' : 'text-bad'}>{habilitada ? 'habilitada (arranque abierto)' : 'deshabilitada (arranque cerrado)'}</strong>
        </p>
        <div className="mt-3">
          {habilitada ? (
            <Button variant="danger" onClick={() => setConfirmar(true)}>
              Cerrar arranque
            </Button>
          ) : (
            <Button onClick={() => fijarArranque(true)} disabled={guardarEtl.isPending}>
              Reabrir carga de Excel
            </Button>
          )}
        </div>
      </Card>

      <Card titulo="Fuente de los reentrenamientos">
        <div className="flex flex-wrap items-end gap-3">
          <Campo etiqueta="Datos usados">
            <select aria-label="Fuente de reentrenamiento" value={fuente} onChange={(e) => setFuente(e.target.value as Fuente)} className={CLASE_INPUT}>
              {FUENTES.map((f) => (
                <option key={f.valor} value={f.valor}>
                  {f.etiqueta}
                </option>
              ))}
            </select>
          </Campo>
          <Button
            variant="primary"
            disabled={guardarEtl.isPending || fuente === etl.data?.fuente_reentrenamiento}
            onClick={() => guardarEtl.mutate({ carga_excel_habilitada: habilitada, fuente_reentrenamiento: fuente })}
          >
            Guardar fuente
          </Button>
        </div>
      </Card>

      <Card titulo="Cuadre de caja">
        <div className="flex flex-wrap items-end gap-3">
          <Campo etiqueta="Umbral de diferencia (Q)">
            <input aria-label="Umbral de diferencia de caja" inputMode="decimal" value={umbral} onChange={(e) => setUmbral(e.target.value)} className={`${CLASE_INPUT} num w-28 text-right`} />
          </Campo>
          <Button variant="primary" disabled={!umbralValido || guardarCaja.isPending} onClick={() => guardarCaja.mutate({ umbral_diferencia_caja: umbral })}>
            Guardar umbral
          </Button>
        </div>
        {guardarCaja.isError && <AlertBanner>{mensajeError(guardarCaja.error)}</AlertBanner>}
        {guardarCaja.isSuccess && <p className="mt-2 text-sm text-good">Umbral actualizado.</p>}
      </Card>

      {confirmar && (
        <Modal
          titulo="Cerrar el arranque"
          onCerrar={() => setConfirmar(false)}
          acciones={
            <>
              <Button onClick={() => setConfirmar(false)}>Cancelar</Button>
              <Button variant="danger" onClick={() => fijarArranque(false)} disabled={guardarEtl.isPending}>
                Cerrar arranque
              </Button>
            </>
          }
        >
          Con el arranque cerrado, <strong>POST /etl/upload-excel</strong> responde 409 y ningún Excel nuevo podrá alimentar el modelo. Los datos ya cargados no se tocan. El cambio queda auditado.
        </Modal>
      )}
    </div>
  )
}
