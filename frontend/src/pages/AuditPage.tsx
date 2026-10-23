import { useCallback, useEffect, useState } from 'react'
import { Card, EmptyState, ErrorAlert, Field, LoadingBlock } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { formatDateTime } from '../lib/format'
import type { AuditList } from '../lib/types'

const PAGE_SIZE = 30

export function AuditPage() {
  const [data, setData] = useState<AuditList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [action, setAction] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(
        await api.get<AuditList>('/audit', {
          action: action || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [action, dateFrom, dateTo, page])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPage(0)
  }, [action, dateFrom, dateTo])

  const pageCount = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-header__title">Журнал действий</h1>
          <p className="page-header__description">
            События создаются серверной логикой. Пароли и секреты в журнал не попадают.
          </p>
        </div>
      </div>

      <Card title="Фильтры">
        <div className="filter-bar">
          <Field label="Тип действия" htmlFor="audit-action">
            <input
              id="audit-action"
              className="input"
              placeholder="payment_occurrence.updated"
              value={action}
              onChange={(event) => setAction(event.target.value)}
              data-testid="audit-action-filter"
            />
          </Field>
          <Field label="С даты" htmlFor="audit-from">
            <input
              id="audit-from"
              type="date"
              className="input"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </Field>
          <Field label="По дату" htmlFor="audit-to">
            <input
              id="audit-to"
              type="date"
              className="input"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </Field>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => {
              setAction('')
              setDateFrom('')
              setDateTo('')
            }}
          >
            Сбросить
          </button>
        </div>
      </Card>

      {error && <ErrorAlert message={error} onRetry={load} />}

      <Card flush>
        {loading ? (
          <LoadingBlock label="Загрузка журнала…" />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon="📋"
            title="Событий не найдено"
            text="Измените фильтры или выполните действие в системе."
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="table table--responsive">
                <thead>
                  <tr>
                    <th scope="col">Время</th>
                    <th scope="col">Пользователь</th>
                    <th scope="col">Действие</th>
                    <th scope="col">Объект</th>
                    <th scope="col">Описание</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((entry) => (
                    <tr key={entry.id} data-testid="audit-row">
                      <td data-label="Время" className="table__meta">
                        {formatDateTime(entry.created_at)}
                      </td>
                      <td data-label="Пользователь">{entry.actor_label}</td>
                      <td data-label="Действие">
                        <code className="text-small">{entry.action}</code>
                      </td>
                      <td data-label="Объект" className="table__meta">
                        {entry.entity_type}
                        {entry.entity_id ? ` #${entry.entity_id}` : ''}
                      </td>
                      <td data-label="Описание">{entry.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div
              className="row row--between"
              style={{ padding: '12px 20px', borderTop: '1px solid var(--color-border)' }}
            >
              <span className="text-small text-muted">
                Страница {page + 1} из {pageCount} · всего {data.total}
              </span>
              <div className="btn-row">
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  disabled={page === 0}
                  onClick={() => setPage((current) => Math.max(0, current - 1))}
                >
                  Назад
                </button>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  disabled={page + 1 >= pageCount}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Вперёд
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  )
}
