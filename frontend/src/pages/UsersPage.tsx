import { useCallback, useEffect, useState } from 'react'
import { Card, EmptyState, ErrorAlert, Field, LoadingBlock, Modal } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'
import { formatDate } from '../lib/format'
import type { UserAccount } from '../lib/types'

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const toast = useToast()
  const [users, setUsers] = useState<UserAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setUsers(await api.get<UserAccount[]>('/users'))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleCreate = async () => {
    if (!username.trim() || password.length < 8) {
      toast.push('Укажите логин и пароль не короче 8 символов', 'error')
      return
    }
    setSaving(true)
    try {
      await api.post('/users', {
        username: username.trim(),
        email: email.trim() || null,
        password,
        role,
      })
      toast.push('Пользователь создан')
      setCreateOpen(false)
      setUsername('')
      setEmail('')
      setPassword('')
      setRole('user')
      await load()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось создать', 'error')
    } finally {
      setSaving(false)
    }
  }

  const toggleRole = async (account: UserAccount) => {
    const nextRole = account.role === 'admin' ? 'user' : 'admin'
    try {
      await api.patch(`/users/${account.id}`, { role: nextRole })
      toast.push('Роль изменена')
      await load()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось изменить роль', 'error')
    }
  }

  const toggleActive = async (account: UserAccount) => {
    try {
      if (account.is_active) {
        await api.delete(`/users/${account.id}`)
        toast.push('Пользователь деактивирован')
      } else {
        await api.patch(`/users/${account.id}`, { is_active: true })
        toast.push('Пользователь активирован')
      }
      await load()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось изменить', 'error')
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-header__title">Пользователи</h1>
          <p className="page-header__description">
            Управление доступом. Bootstrap-администратор защищён от удаления и понижения в правах.
          </p>
        </div>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setCreateOpen(true)}
          data-testid="create-user-button"
        >
          + Новый пользователь
        </button>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}

      <Card flush>
        {loading ? (
          <LoadingBlock label="Загрузка пользователей…" />
        ) : users.length === 0 ? (
          <EmptyState icon="👤" title="Пользователей нет" text="Создайте первого пользователя." />
        ) : (
          <div className="table-wrap">
            <table className="table table--responsive">
              <thead>
                <tr>
                  <th scope="col">Логин</th>
                  <th scope="col">Роль</th>
                  <th scope="col">Состояние</th>
                  <th scope="col">Создан</th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {users.map((account) => {
                  const isSelf = account.id === currentUser?.id
                  const locked = account.is_bootstrap || isSelf
                  return (
                    <tr key={account.id} data-testid="user-row">
                      <td data-label="Логин">
                        <div className="table__title">{account.username}</div>
                        {account.email && <div className="table__meta">{account.email}</div>}
                      </td>
                      <td data-label="Роль">
                        <span
                          className={
                            account.role === 'admin' ? 'badge badge--pending' : 'badge badge--neutral'
                          }
                        >
                          {account.role === 'admin' ? 'Администратор' : 'Пользователь'}
                        </span>
                        {account.is_bootstrap && (
                          <div className="table__meta">bootstrap-аккаунт</div>
                        )}
                      </td>
                      <td data-label="Состояние">
                        <span
                          className={
                            account.is_active ? 'badge badge--paid' : 'badge badge--overdue'
                          }
                        >
                          <span className="badge__dot" aria-hidden="true" />
                          {account.is_active ? 'Активен' : 'Отключён'}
                        </span>
                      </td>
                      <td data-label="Создан">{formatDate(account.created_at.slice(0, 10))}</td>
                      <td data-label="Действия">
                        <div className="table__actions">
                          {locked ? (
                            <span className="text-tiny text-muted">
                              {account.is_bootstrap ? 'Защищён' : 'Текущая сессия'}
                            </span>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={() => toggleRole(account)}
                              >
                                {account.role === 'admin' ? 'Сделать пользователем' : 'Сделать админом'}
                              </button>
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={() => toggleActive(account)}
                              >
                                {account.is_active ? 'Деактивировать' : 'Активировать'}
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={createOpen}
        title="Новый пользователь"
        description="Пароль хранится только в виде хеша и не отображается после создания."
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <button type="button" className="btn btn--secondary" onClick={() => setCreateOpen(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={handleCreate}
              disabled={saving}
              data-testid="submit-user-form"
            >
              {saving ? 'Создание…' : 'Создать'}
            </button>
          </>
        }
      >
        <div className="stack">
          <Field label="Логин" htmlFor="new-username">
            <input
              id="new-username"
              className="input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              data-testid="user-username-input"
            />
          </Field>
          <Field label="Email" htmlFor="new-email" hint="Необязательно">
            <input
              id="new-email"
              type="email"
              className="input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label="Пароль" htmlFor="new-password" hint="Минимум 8 символов">
            <input
              id="new-password"
              type="password"
              className="input"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              data-testid="user-password-input"
            />
          </Field>
          <Field label="Роль" htmlFor="new-role">
            <select
              id="new-role"
              className="select"
              value={role}
              onChange={(event) => setRole(event.target.value as 'user' | 'admin')}
            >
              <option value="user">Пользователь</option>
              <option value="admin">Администратор</option>
            </select>
          </Field>
        </div>
      </Modal>
    </>
  )
}
