import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, ErrorAlert, LoadingBlock, StatusBadge } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { dueHint, formatAmount, formatDate, formatDateTime } from '../lib/format'
import type { Dashboard } from '../lib/types'

export function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get<Dashboard>('/dashboard'))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return <LoadingBlock label="Загрузка dashboard…" />
  if (error) return <ErrorAlert message={error} onRetry={load} />
  if (!data) return null

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-header__title">Dashboard</h1>
          <p className="page-header__description">
            Сегодня {formatDate(data.today)} · часовой пояс {data.timezone}
          </p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={load}>
          Обновить
        </button>
      </div>

      <div className="stat-grid">
        <div className="stat" data-testid="stat-upcoming">
          <div className="stat__label">Предстоящие платежи</div>
          <div className="currency-list">
            {data.totals.map((total) => (
              <div className="currency-row" key={total.currency}>
                <span className="currency-row__code">{total.currency}</span>
                <span className="currency-row__amount">
                  {formatAmount(total.upcoming, total.currency)}
                </span>
              </div>
            ))}
          </div>
          <div className="stat__hint">По каждой валюте отдельно</div>
        </div>

        <div className="stat" data-testid="stat-overdue">
          <div className="stat__label">
            <span className="badge badge--overdue">
              <span className="badge__dot" aria-hidden="true" />
              Просрочено
            </span>
          </div>
          <div className="currency-list">
            {data.totals.map((total) => (
              <div className="currency-row" key={total.currency}>
                <span className="currency-row__code">{total.currency}</span>
                <span className="currency-row__amount">
                  {formatAmount(total.overdue, total.currency)}
                </span>
              </div>
            ))}
          </div>
          <div className="stat__hint">{data.overdue_count} периодов с истёкшим сроком</div>
        </div>

        <div className="stat" data-testid="stat-due-soon">
          <div className="stat__label">Срок скоро наступит</div>
          <div className="stat__value">{data.due_soon_count}</div>
          <div className="stat__hint">В ближайшие 3 дня</div>
        </div>

        <div className="stat" data-testid="stat-paid">
          <div className="stat__label">Оплачено за месяц</div>
          <div className="stat__value">{data.paid_count}</div>
          <div className="stat__hint">Периодов отмечено оплаченными</div>
        </div>
      </div>

      <div className="grid-2">
        <Card
          title="Ближайшие сроки"
          subtitle="Периоды, требующие внимания"
          actions={
            <Link className="btn btn--secondary btn--sm" to="/payments">
              Все платежи
            </Link>
          }
          flush
        >
          {data.upcoming.length === 0 ? (
            <EmptyState
              icon="✅"
              title="Нет ближайших платежей"
              text="Все периоды оплачены или ещё не сгенерированы."
            />
          ) : (
            <div className="table-wrap">
              <table className="table table--responsive">
                <thead>
                  <tr>
                    <th scope="col">Платёж</th>
                    <th scope="col">Срок</th>
                    <th scope="col">Сумма</th>
                    <th scope="col">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {data.upcoming.map((item) => (
                    <tr key={item.id}>
                      <td data-label="Платёж">
                        <Link to={`/payments/${item.recurring_payment_id}`} className="table__title">
                          {item.payment_title}
                        </Link>
                        <div className="table__meta">{dueHint(item)}</div>
                      </td>
                      <td data-label="Срок">{formatDate(item.due_date)}</td>
                      <td data-label="Сумма" className="table__amount">
                        {formatAmount(item.amount, item.currency)}
                      </td>
                      <td data-label="Статус">
                        <StatusBadge status={item.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Каналы уведомлений" subtitle="Состояние интеграций">
          <div className="stack stack--tight">
            <IntegrationRow
              name="Telegram"
              configured={data.integrations.telegram_configured}
              hint={data.integrations.telegram_hint}
            />
            <IntegrationRow
              name="Email (SMTP)"
              configured={data.integrations.smtp_configured}
              hint={data.integrations.smtp_hint}
            />
          </div>
        </Card>
      </div>

      <Card title="Последние изменения" subtitle="Общая история действий" flush>
        {data.recent_activity.length === 0 ? (
          <EmptyState icon="🗒" title="Пока нет событий" text="Действия пользователей появятся здесь." />
        ) : (
          <div className="table-wrap">
            <table className="table table--responsive">
              <thead>
                <tr>
                  <th scope="col">Время</th>
                  <th scope="col">Пользователь</th>
                  <th scope="col">Действие</th>
                  <th scope="col">Описание</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_activity.map((entry) => (
                  <tr key={entry.id}>
                    <td data-label="Время" className="table__meta">
                      {formatDateTime(entry.created_at)}
                    </td>
                    <td data-label="Пользователь">{entry.actor_label}</td>
                    <td data-label="Действие">
                      <code className="text-small">{entry.action}</code>
                    </td>
                    <td data-label="Описание">{entry.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}

function IntegrationRow({
  name,
  configured,
  hint,
}: {
  name: string
  configured: boolean
  hint: string | null
}) {
  return (
    <div className="row row--between" style={{ padding: '8px 0' }}>
      <div>
        <div style={{ fontWeight: 500 }}>{name}</div>
        {hint && <div className="text-tiny text-muted">{hint}</div>}
      </div>
      <span className={configured ? 'badge badge--paid' : 'badge badge--neutral'}>
        <span className="badge__dot" aria-hidden="true" />
        {configured ? 'Настроено' : 'Не настроено'}
      </span>
    </div>
  )
}
