import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, ErrorAlert, LoadingBlock, StatusBadge } from '../components/ui'
import { ApiError, api } from '../lib/api'
import {
  CURRENCIES,
  STATUS_LABELS,
  STATUS_ORDER,
  currentMonthKey,
  formatAmount,
  formatDate,
  monthLabel,
  shiftMonth,
} from '../lib/format'
import type { CalendarMonth, Currency, Occurrence, PaymentStatus } from '../lib/types'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

export function CalendarPage() {
  const [month, setMonth] = useState(currentMonthKey())
  const [data, setData] = useState<CalendarMonth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currency, setCurrency] = useState<Currency | ''>('')
  const [status, setStatus] = useState<PaymentStatus | ''>('')
  const [selectedDay, setSelectedDay] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(
        await api.get<CalendarMonth>('/calendar', {
          month,
          currency: currency || undefined,
          status: status || undefined,
        }),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [month, currency, status])

  useEffect(() => {
    void load()
  }, [load])

  const grid = useMemo(() => {
    if (!data) return []
    const [year, monthNumber] = data.month.split('-').map(Number)
    const firstOfMonth = new Date(Date.UTC(year, monthNumber - 1, 1))
    // ISO weekday: Monday = 1 … Sunday = 7
    const offset = (firstOfMonth.getUTCDay() + 6) % 7
    const cells: Array<{ date: string; inMonth: boolean; items: Occurrence[] }> = []

    for (let index = 0; index < offset; index += 1) {
      const day = new Date(Date.UTC(year, monthNumber - 1, 1 - (offset - index)))
      cells.push({ date: day.toISOString().slice(0, 10), inMonth: false, items: [] })
    }

    for (const day of data.days) {
      cells.push({ date: day.date, inMonth: true, items: day.items })
    }

    while (cells.length % 7 !== 0) {
      const last = new Date(`${cells[cells.length - 1].date}T00:00:00Z`)
      last.setUTCDate(last.getUTCDate() + 1)
      cells.push({ date: last.toISOString().slice(0, 10), inMonth: false, items: [] })
    }
    return cells
  }, [data])

  const selectedItems = useMemo(() => {
    if (!selectedDay) return []
    return grid.find((cell) => cell.date === selectedDay)?.items ?? []
  }, [grid, selectedDay])

  const today = new Date().toISOString().slice(0, 10)

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-header__title">Календарь платежей</h1>
          <p className="page-header__description">
            Реальные периоды из базы данных. Просрочка начинается на следующий день после срока.
          </p>
        </div>
      </div>

      <Card>
        <div className="row row--between">
          <div className="btn-row">
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setMonth((current) => shiftMonth(current, -1))}
              aria-label="Предыдущий месяц"
            >
              ←
            </button>
            <strong style={{ minWidth: '160px', textAlign: 'center' }}>
              {monthLabel(month)}
            </strong>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setMonth((current) => shiftMonth(current, 1))}
              aria-label="Следующий месяц"
            >
              →
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => setMonth(currentMonthKey())}
            >
              Текущий месяц
            </button>
          </div>

          <div className="btn-row">
            <select
              className="select"
              value={currency}
              onChange={(event) => setCurrency(event.target.value as Currency | '')}
              aria-label="Фильтр по валюте"
              data-testid="calendar-currency"
            >
              <option value="">Все валюты</option>
              {CURRENCIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={status}
              onChange={(event) => setStatus(event.target.value as PaymentStatus | '')}
              aria-label="Фильтр по статусу"
            >
              <option value="">Все статусы</option>
              {STATUS_ORDER.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {error && <ErrorAlert message={error} onRetry={load} />}

      {loading ? (
        <LoadingBlock label="Загрузка календаря…" />
      ) : (
        <>
          <div className="calendar" role="grid" aria-label={`Календарь на ${monthLabel(month)}`}>
            {WEEKDAYS.map((day) => (
              <div className="calendar__weekday" key={day} role="columnheader">
                {day}
              </div>
            ))}
            {grid.map((cell) => {
              const classes = ['calendar__day']
              if (!cell.inMonth) classes.push('calendar__day--muted')
              if (cell.date === today) classes.push('calendar__day--today')
              if (cell.date === selectedDay) classes.push('calendar__day--selected')
              return (
                <button
                  type="button"
                  key={cell.date}
                  className={classes.join(' ')}
                  onClick={() => setSelectedDay(cell.date)}
                  aria-label={`${cell.date}, платежей: ${cell.items.length}`}
                >
                  <span className="calendar__day-number">{Number(cell.date.slice(8, 10))}</span>
                  {cell.items.slice(0, 2).map((item) => (
                    <span
                      key={item.id}
                      className={`calendar__event calendar__event--${item.status}`}
                      title={`${item.payment_title} · ${formatAmount(item.amount, item.currency)}`}
                    >
                      {item.payment_title}
                    </span>
                  ))}
                  {cell.items.length > 2 && (
                    <span className="calendar__more">ещё {cell.items.length - 2}</span>
                  )}
                </button>
              )
            })}
          </div>

          {selectedDay && (
            <Card
              title={`Платежи на ${formatDate(selectedDay)}`}
              subtitle={selectedItems.length ? `${selectedItems.length} период(ов)` : 'Нет платежей'}
              flush
            >
              {selectedItems.length === 0 ? (
                <EmptyState icon="🗓" title="На эту дату платежей нет" text="Выберите другой день." />
              ) : (
                <div className="table-wrap">
                  <table className="table table--responsive">
                    <thead>
                      <tr>
                        <th scope="col">Платёж</th>
                        <th scope="col">Сумма</th>
                        <th scope="col">Статус</th>
                        <th scope="col">Оплачено</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedItems.map((item) => (
                        <tr key={item.id}>
                          <td data-label="Платёж">
                            <Link to={`/payments/${item.recurring_payment_id}`}>
                              {item.payment_title}
                            </Link>
                          </td>
                          <td data-label="Сумма" className="table__amount">
                            {formatAmount(item.amount, item.currency)}
                          </td>
                          <td data-label="Статус">
                            <StatusBadge status={item.status} />
                          </td>
                          <td data-label="Оплачено">{formatDate(item.paid_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </>
  )
}
