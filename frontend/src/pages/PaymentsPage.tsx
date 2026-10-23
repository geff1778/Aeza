import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, ErrorAlert, LoadingBlock, StatusBadge } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'
import {
  CURRENCIES,
  STATUS_LABELS,
  STATUS_ORDER,
  dueHint,
  formatAmount,
  formatDate,
} from '../lib/format'
import type { Currency, Occurrence, OccurrenceList, PaymentStatus, RecurringPayment } from '../lib/types'
import { PayModal } from '../features/PayModal'
import { PaymentFormModal } from '../features/PaymentFormModal'

const PAGE_SIZE = 20

export function PaymentsPage() {
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [items, setItems] = useState<Occurrence[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [payments, setPayments] = useState<RecurringPayment[]>([])

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [status, setStatus] = useState<PaymentStatus | ''>('')
  const [currency, setCurrency] = useState<Currency | ''>('')
  const [paymentId, setPaymentId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sort, setSort] = useState('due_date')
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(0)

  const [payTarget, setPayTarget] = useState<Occurrence | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setPage(0)
  }, [debouncedSearch, status, currency, paymentId, dateFrom, dateTo, sort, direction])

  const loadOccurrences = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<OccurrenceList>('/payment-occurrences', {
        search: debouncedSearch || undefined,
        status: status || undefined,
        currency: currency || undefined,
        recurring_payment_id: paymentId || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort,
        direction,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setItems(data.items)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [debouncedSearch, status, currency, paymentId, dateFrom, dateTo, sort, direction, page])

  useEffect(() => {
    void loadOccurrences()
  }, [loadOccurrences])

  useEffect(() => {
    void api
      .get<RecurringPayment[]>('/recurring-payments')
      .then(setPayments)
      .catch(() => setPayments([]))
  }, [])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const activeFilterCount = useMemo(
    () =>
      [debouncedSearch, status, currency, paymentId, dateFrom, dateTo].filter(Boolean).length,
    [debouncedSearch, status, currency, paymentId, dateFrom, dateTo],
  )

  const resetFilters = () => {
    setSearch('')
    setStatus('')
    setCurrency('')
    setPaymentId('')
    setDateFrom('')
    setDateTo('')
  }

  const toggleSort = (column: string) => {
    if (sort === column) {
      setDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(column)
      setDirection('asc')
    }
  }

  const handleMarkPaid = async (occurrence: Occurrence) => {
    try {
      await api.patch(`/payment-occurrences/${occurrence.id}`, { is_paid: true })
      toast.push(`«${occurrence.payment_title}» отмечен как оплаченный`)
      await loadOccurrences()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось сохранить', 'error')
    }
  }

  const handleUnmark = async (occurrence: Occurrence) => {
    try {
      await api.patch(`/payment-occurrences/${occurrence.id}`, { is_paid: false })
      toast.push('Отметка об оплате снята')
      await loadOccurrences()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось сохранить', 'error')
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-header__title">Платежи</h1>
          <p className="page-header__description">
            Общая история периодов всех пользователей. Найдено: {total}
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => setFormOpen(true)}
            data-testid="create-payment-button"
          >
            + Новый регулярный платёж
          </button>
        )}
      </div>

      <Card title="Фильтры" subtitle={activeFilterCount ? `Активно фильтров: ${activeFilterCount}` : 'Показаны все периоды'}>
        <div className="filter-bar">
          <div className="field" style={{ flex: '1 1 220px' }}>
            <label className="field__label" htmlFor="search">
              Поиск
            </label>
            <input
              id="search"
              className="input"
              placeholder="Название платежа…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              data-testid="search-input"
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="filter-status">
              Статус
            </label>
            <select
              id="filter-status"
              className="select"
              value={status}
              onChange={(event) => setStatus(event.target.value as PaymentStatus | '')}
              data-testid="filter-status"
            >
              <option value="">Все</option>
              {STATUS_ORDER.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="filter-currency">
              Валюта
            </label>
            <select
              id="filter-currency"
              className="select"
              value={currency}
              onChange={(event) => setCurrency(event.target.value as Currency | '')}
              data-testid="filter-currency"
            >
              <option value="">Все</option>
              {CURRENCIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="filter-payment">
              Регулярный платёж
            </label>
            <select
              id="filter-payment"
              className="select"
              value={paymentId}
              onChange={(event) => setPaymentId(event.target.value)}
            >
              <option value="">Все</option>
              {payments.map((payment) => (
                <option key={payment.id} value={payment.id}>
                  {payment.title}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="date-from">
              С даты
            </label>
            <input
              id="date-from"
              type="date"
              className="input"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="date-to">
              По дату
            </label>
            <input
              id="date-to"
              type="date"
              className="input"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </div>

          <button type="button" className="btn btn--secondary" onClick={resetFilters}>
            Сбросить
          </button>
        </div>
      </Card>

      {error && <ErrorAlert message={error} onRetry={loadOccurrences} />}

      <Card flush>
        {loading ? (
          <LoadingBlock label="Загрузка платежей…" />
        ) : items.length === 0 ? (
          <EmptyState
            icon="🔍"
            title={activeFilterCount ? 'Ничего не найдено' : 'Платежей пока нет'}
            text={
              activeFilterCount
                ? 'Измените условия фильтрации или сбросьте фильтры.'
                : isAdmin
                  ? 'Создайте первый регулярный платёж — система сформирует периоды оплаты.'
                  : 'Администратор ещё не добавил регулярные платежи.'
            }
            action={
              activeFilterCount ? (
                <button type="button" className="btn btn--secondary" onClick={resetFilters}>
                  Сбросить фильтры
                </button>
              ) : isAdmin ? (
                <button type="button" className="btn btn--primary" onClick={() => setFormOpen(true)}>
                  Создать платёж
                </button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="table table--responsive table--sortable">
                <thead>
                  <tr>
                    <th scope="col">Платёж</th>
                    <th
                      scope="col"
                      aria-sort={sort === 'due_date' ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                      onClick={() => toggleSort('due_date')}
                    >
                      Срок
                      {sort === 'due_date' && (
                        <span className="sort-indicator">{direction === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      scope="col"
                      aria-sort={sort === 'amount' ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                      onClick={() => toggleSort('amount')}
                    >
                      Сумма
                      {sort === 'amount' && (
                        <span className="sort-indicator">{direction === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th scope="col">Статус</th>
                    <th scope="col">Оплачено</th>
                    <th scope="col">Чек</th>
                    <th scope="col" style={{ textAlign: 'right' }}>
                      Действия
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} data-testid="payment-row">
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
                      <td data-label="Оплачено">{formatDate(item.paid_at)}</td>
                      <td data-label="Чек">
                        {item.receipt_url ? (
                          <a href={item.receipt_url} target="_blank" rel="noreferrer noopener">
                            Ссылка
                          </a>
                        ) : item.attachment_count > 0 ? (
                          <span className="text-small text-muted">{item.attachment_count} файл(а)</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td data-label="Действия">
                        <div className="table__actions">
                          {item.is_paid ? (
                            <>
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={() => setPayTarget(item)}
                                data-testid="edit-paid-date"
                              >
                                Изменить дату
                              </button>
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={() => handleUnmark(item)}
                                data-testid="unmark-paid"
                              >
                                Снять отметку
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="btn btn--success btn--sm"
                                onClick={() => handleMarkPaid(item)}
                                data-testid="mark-paid"
                              >
                                Оплачено
                              </button>
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={() => setPayTarget(item)}
                              >
                                Указать дату
                              </button>
                            </>
                          )}
                        </div>
                      </td>
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
                Страница {page + 1} из {pageCount} · всего {total}
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

      <PayModal
        occurrence={payTarget}
        onClose={() => setPayTarget(null)}
        onSaved={() => {
          setPayTarget(null)
          void loadOccurrences()
        }}
      />

      <PaymentFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={() => {
          setFormOpen(false)
          void loadOccurrences()
          void api.get<RecurringPayment[]>('/recurring-payments').then(setPayments)
        }}
      />
    </>
  )
}
