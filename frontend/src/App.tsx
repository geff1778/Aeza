import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LoadingBlock } from './components/ui'
import { useAuth } from './lib/auth'
import { AuditPage } from './pages/AuditPage'
import { BudgetsPage } from './pages/BudgetsPage'
import { CalendarPage } from './pages/CalendarPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { PaymentDetailPage } from './pages/PaymentDetailPage'
import { PaymentsPage } from './pages/PaymentsPage'
import { UsersPage } from './pages/UsersPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <LoadingBlock label="Проверка сессии…" />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <LoadingBlock label="Проверка прав…" />
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/" replace />
  return <>{children}</>
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/payments" element={<PaymentsPage />} />
        <Route path="/payments/:id" element={<PaymentDetailPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/budgets" element={<BudgetsPage />} />
        <Route
          path="/users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/audit"
          element={
            <RequireAdmin>
              <AuditPage />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
