import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'
import type { Dashboard } from '../lib/types'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '◫', end: true },
  { to: '/payments', label: 'Платежи', icon: '≡' },
  { to: '/calendar', label: 'Календарь', icon: '▦' },
  { to: '/budgets', label: 'Бюджеты', icon: '◐' },
]

const ADMIN_ITEMS = [
  { to: '/users', label: 'Пользователи', icon: '◎' },
  { to: '/audit', label: 'Журнал действий', icon: '☰' },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [overdueCount, setOverdueCount] = useState<number | null>(null)

  const loadBadge = useCallback(async () => {
    try {
      const dashboard = await api.get<Dashboard>('/dashboard')
      setOverdueCount(dashboard.overdue_count)
    } catch {
      setOverdueCount(null)
    }
  }, [])

  useEffect(() => {
    void loadBadge()
  }, [loadBadge, location.pathname])

  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const initials = user?.username.slice(0, 2).toUpperCase() ?? '??'

  return (
    <div className="app-shell">
      <aside className={sidebarOpen ? 'sidebar sidebar--open' : 'sidebar'}>
        <div className="brand">
          <div className="brand__mark" aria-hidden="true">
            IK
          </div>
          <div>
            <div className="brand__name">Invoice Keeper</div>
            <div className="brand__tagline">Регулярные платежи</div>
          </div>
        </div>

        <nav className="nav" aria-label="Основная навигация">
          <div className="nav__label">Работа</div>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
            >
              <span className="nav__icon" aria-hidden="true">
                {item.icon}
              </span>
              {item.label}
              {item.to === '/' && overdueCount ? (
                <span className="nav__badge" title="Просроченных платежей">
                  {overdueCount}
                </span>
              ) : null}
            </NavLink>
          ))}

          {user?.role === 'admin' && (
            <>
              <div className="nav__label">Администрирование</div>
              {ADMIN_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
                >
                  <span className="nav__icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                </NavLink>
              ))}
            </>
          )}
        </nav>

        <div className="sidebar__footer">
          <div className="user-chip">
            <div className="user-chip__avatar" aria-hidden="true">
              {initials}
            </div>
            <div className="user-chip__meta">
              <div className="user-chip__name">{user?.username}</div>
              <div className="user-chip__role">
                {user?.role === 'admin' ? 'Администратор' : 'Пользователь'}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--block"
            onClick={handleLogout}
            data-testid="logout-button"
          >
            Выйти
          </button>
        </div>
      </aside>

      {sidebarOpen && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(16,24,40,0.35)' }}
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-btn menu-toggle"
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label="Открыть меню"
            aria-expanded={sidebarOpen}
          >
            ☰
          </button>
          <div>
            <div className="topbar__title">Invoice Keeper</div>
            <div className="topbar__subtitle">Учёт регулярных расходов и сроков оплаты</div>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
