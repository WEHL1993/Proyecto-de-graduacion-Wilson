import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { PermissionGate } from '../components/common/PermissionGate'
import { AccessDeniedView } from '../views/AccessDeniedView'
import { LoginView } from '../views/LoginView'
import { ModelMonitoringView } from '../views/ModelMonitoringView'
import { SalesDashboardView } from '../views/SalesDashboardView'
import { useAuth } from './providers/AuthProvider'
import { PERMISOS_VISTA } from './rbac'

/** Inicio: la primera vista a la que el rol tiene acceso (evita caer en «denegado» al entrar). */
function Inicio() {
  const { canAny } = useAuth()
  if (canAny(PERMISOS_VISTA.dashboard)) return <SalesDashboardView />
  if (canAny(PERMISOS_VISTA.monitoreo)) return <Navigate to="/monitoreo" replace />
  return <Navigate to="/acceso-denegado" replace />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginView />} />
      <Route
        element={
          <PermissionGate guardRoute anyOf={[]}>
            <AppShell />
          </PermissionGate>
        }
      >
        <Route index element={<Inicio />} />
        <Route
          path="monitoreo"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.monitoreo}>
              <ModelMonitoringView />
            </PermissionGate>
          }
        />
        <Route path="acceso-denegado" element={<AccessDeniedView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
