import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to="/" replace />

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError('Не удалось войти. Попробуйте ещё раз.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__brand">
          <div className="brand__mark" aria-hidden="true">
            IK
          </div>
          <div>
            <div className="login-card__title">Invoice Keeper</div>
            <div className="brand__tagline">Регулярные платежи</div>
          </div>
        </div>

        <p className="login-card__subtitle">
          Войдите, чтобы видеть общий список платежей, сроки и просрочки.
        </p>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: '16px' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="stack">
          <div className="field">
            <label className="field__label" htmlFor="username">
              Логин
            </label>
            <input
              id="username"
              name="username"
              className="input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
              autoFocus
              data-testid="login-username"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="password">
              Пароль
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className="input"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              data-testid="login-password"
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary btn--block"
            disabled={submitting}
            data-testid="login-submit"
          >
            {submitting ? 'Вход…' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  )
}
