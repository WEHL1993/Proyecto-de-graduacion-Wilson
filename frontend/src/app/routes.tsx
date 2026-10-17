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

/** Inicio: la pantalla configurada para el rol en la BD (o la primera del menú autorizado). */
function Inicio() {
  const { usuario, puedeVer } = useAuth()
  const destino = usuario?.pantalla_inicio
  if (puedeVer('dashboard')) return <SalesDashboardView />
  return <Navigate to={destino && destino !== '/' ? destino : '/acceso-denegado'} replace />
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
            <PermissionGate guardRoute pantalla="monitoreo">
              <ModelMonitoringView />
            </PermissionGate>
          }
        />
        <Route
          path="compras"
          element={
            <PermissionGate guardRoute pantalla="compras">
              <PurchasingView />
            </PermissionGate>
          }
        />
        <Route
          path="inventario"
          element={
            <PermissionGate guardRoute pantalla="inventario">
              <InventoryView />
            </PermissionGate>
          }
        />
        <Route
          path="productos"
          element={
            <PermissionGate guardRoute pantalla="productos">
              <ProductsView />
            </PermissionGate>
          }
        />
        <Route
          path="catalogos/rutas"
          element={
            <PermissionGate guardRoute pantalla="catalogos">
              <RoutesAdminView />
            </PermissionGate>
          }
        />
        <Route
          path="catalogos/rutas/:rutaId/equipo"
          element={
            <PermissionGate guardRoute pantalla="catalogos">
              <RouteTeamView />
            </PermissionGate>
          }
        />
        <Route
          path="catalogos/empleados"
          element={
            <PermissionGate guardRoute pantalla="catalogos">
              <EmployeesView />
            </PermissionGate>
          }
        />
        <Route
          path="ventas/liquidacion"
          element={
            <PermissionGate guardRoute pantalla="liquidacion">
              <LiquidacionDiariaView />
            </PermissionGate>
          }
        />
        <Route
          path="ventas/liquidaciones"
          element={
            <PermissionGate guardRoute pantalla="liquidaciones">
              <LiquidacionesHistorialView />
            </PermissionGate>
          }
        />
        <Route
          path="politica-datos"
          element={
            <PermissionGate guardRoute pantalla="politica_datos">
              <PoliticaDatosView />
            </PermissionGate>
          }
        />
        <Route
          path="etl"
          element={
            <PermissionGate guardRoute pantalla="etl">
              <EtlUploadView />
            </PermissionGate>
          }
        />
        <Route
          path="reportes"
          element={
            <PermissionGate guardRoute pantalla="reportes">
              <ReportsView />
            </PermissionGate>
          }
        />
        <Route
          path="usuarios"
          element={
            <PermissionGate guardRoute pantalla="usuarios">
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
