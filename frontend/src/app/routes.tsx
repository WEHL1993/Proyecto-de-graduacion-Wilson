import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { PermissionGate } from '../components/common/PermissionGate'
import { AccessDeniedView } from '../views/AccessDeniedView'
import { AdminUsersView } from '../views/AdminUsersView'
import { EmployeesView } from '../views/EmployeesView'
import { EtlUploadView } from '../views/EtlUploadView'
import { InventoryView } from '../views/InventoryView'
import { LiquidacionDiariaView } from '../views/LiquidacionDiariaView'
import { LiquidacionesHistorialView } from '../views/LiquidacionesHistorialView'
import { LoginView } from '../views/LoginView'
import { ModelMonitoringView } from '../views/ModelMonitoringView'
import { RoutesAdminView } from '../views/RoutesAdminView'
import { RouteTeamView } from '../views/RouteTeamView'
import { PoliticaDatosView } from '../views/PoliticaDatosView'
import { ProductsView } from '../views/ProductsView'
import { PurchasingView } from '../views/PurchasingView'
import { ReportsView } from '../views/ReportsView'
import { SalesDashboardView } from '../views/SalesDashboardView'
import { useAuth } from './providers/AuthProvider'
import { PERMISOS_VISTA } from './rbac'

/** Inicio: la primera vista a la que el rol tiene acceso (evita caer en «denegado» al entrar). */
function Inicio() {
  const { canAny } = useAuth()
  if (canAny(PERMISOS_VISTA.dashboard)) return <SalesDashboardView />
  if (canAny(PERMISOS_VISTA.monitoreo)) return <Navigate to="/monitoreo" replace />
  if (canAny(PERMISOS_VISTA.compras)) return <Navigate to="/compras" replace />
  if (canAny(PERMISOS_VISTA.inventario)) return <Navigate to="/inventario" replace />
  if (canAny(PERMISOS_VISTA.liquidacion)) return <Navigate to="/ventas/liquidacion" replace />
  if (canAny(PERMISOS_VISTA.liquidaciones)) return <Navigate to="/ventas/liquidaciones" replace />
  if (canAny(PERMISOS_VISTA.etl)) return <Navigate to="/etl" replace />
  if (canAny(PERMISOS_VISTA.reportes)) return <Navigate to="/reportes" replace />
  if (canAny(PERMISOS_VISTA.usuarios)) return <Navigate to="/usuarios" replace />
  if (canAny(PERMISOS_VISTA.catalogos)) return <Navigate to="/catalogos/rutas" replace />
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
        <Route
          path="compras"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.compras}>
              <PurchasingView />
            </PermissionGate>
          }
        />
        <Route
          path="inventario"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.inventario}>
              <InventoryView />
            </PermissionGate>
          }
        />
        <Route
          path="productos"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.productos}>
              <ProductsView />
            </PermissionGate>
          }
        />
        <Route
          path="catalogos/rutas"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.catalogos}>
              <RoutesAdminView />
            </PermissionGate>
          }
        />
        <Route
          path="catalogos/rutas/:rutaId/equipo"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.catalogos}>
              <RouteTeamView />
            </PermissionGate>
          }
        />
        <Route
          path="catalogos/empleados"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.catalogos}>
              <EmployeesView />
            </PermissionGate>
          }
        />
        <Route
          path="ventas/liquidacion"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.liquidacion}>
              <LiquidacionDiariaView />
            </PermissionGate>
          }
        />
        <Route
          path="ventas/liquidaciones"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.liquidaciones}>
              <LiquidacionesHistorialView />
            </PermissionGate>
          }
        />
        <Route
          path="politica-datos"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.etlConfig}>
              <PoliticaDatosView />
            </PermissionGate>
          }
        />
        <Route
          path="etl"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.etl}>
              <EtlUploadView />
            </PermissionGate>
          }
        />
        <Route
          path="reportes"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.reportes}>
              <ReportsView />
            </PermissionGate>
          }
        />
        <Route
          path="usuarios"
          element={
            <PermissionGate guardRoute anyOf={PERMISOS_VISTA.usuarios}>
              <AdminUsersView />
            </PermissionGate>
          }
        />
        <Route path="acceso-denegado" element={<AccessDeniedView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
