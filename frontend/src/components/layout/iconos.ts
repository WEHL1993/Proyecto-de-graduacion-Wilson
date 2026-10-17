import {
  Boxes,
  CircleDot,
  FileBarChart,
  History,
  LayoutDashboard,
  LineChart,
  Package,
  Receipt,
  Route,
  ShieldCheck,
  ShoppingCart,
  Upload,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** Icono de cada pantalla según su clave en la BD (`pantallas.clave`). */
const ICONOS: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  monitoreo: LineChart,
  compras: ShoppingCart,
  inventario: Boxes,
  productos: Package,
  liquidacion: Receipt,
  liquidaciones: History,
  catalogos: Route,
  etl: Upload,
  politica_datos: ShieldCheck,
  reportes: FileBarChart,
  usuarios: Users,
}

export const iconoDePantalla = (clave: string): LucideIcon => ICONOS[clave] ?? CircleDot
