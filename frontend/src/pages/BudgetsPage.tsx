import { useCallback, useEffect, useState } from 'react'
import { Card, EmptyState, ErrorAlert, Field, LoadingBlock, Modal, ProgressBar } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'
import { CURRENCIES, currentMonthKey, formatAmount, monthLabel } from '../lib/format'
import type { Budget, BudgetPeriod, Currency } from '../lib/types'

export function BudgetsPage() {
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [periodType, setPeriodType] = useState<BudgetPeriod>('month')
  const [periodKey, setPeriodKey] = useState(currentMonthKey())
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editTarget, setEditTarget] = useState<Currency | null>(null)
  const [limitValue, setLimitValue] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setBudgets(
        await api.get<Budget[]>('/budgets', { period_type: periodType, period_key: periodKey }),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [periodType, periodKey])

  useEffect(() => {
    void load()
  }, [load])

  const handleSave = async () => {
    if (!editTarget) return
    const amount = Number(limitValue)
    if (!limitValue || Number.isNaN(amount) || amount <= 0) {
      toast.push('Лимит должен быть больше нуля', 'error')
      return
    }
    setSaving(true)
    try {
      await api.put('/budgets', {
        period_type: periodType,
        period_key: periodKey,
        currency: editTarget,
        limit_amount: limitValue,
      })
      toast.push('Бюджет сохранён')
      setEditTarget(null)
      await load()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось сохранить', 'error')
    } finally {
      setSaving(false)
    }
  }

  const byCurrency = new Map(budgets.map((budget) => [budget.currency, budget]))

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-header__title">Бюджеты</h1>
          <p className="page-header__description">
            Лимиты задаются отдельно для каждой валюты. Планируемые суммы — все запланированные
            периоды, фактические — только оплаченные.
          </p>
        </div>
      </div>

      <Card>
        <div className="filter-bar">
          <Field label="Тип периода" htmlFor="period-type">
            <select
              id="period-type"
              className="select"
              value={periodType}
              onChange={(event) => {
                const value = event.target.value as BudgetPeriod
                setPeriodType(value)
                setPeriodKey(value === 'month' ? currentMonthKey() : currentMonthKey().slice(0, 4))
              }}
              data-testid="budget-period-type"
            >
              <option value="month">Месяц</option>
              <option value="year">Год</option>
            </select>
          </Field>

          <Field label={periodType === 'month' ? 'Месяц' : 'Год'} htmlFor="period-key">
            {periodType === 'month' ? (
              <input
                id="period-key"
                type="month"
                className="input"
                value={periodKey}
                onChange={(event) => setPeriodKey(event.target.value)}
                data-testid="budget-period-key"
              />
            ) : (
              <input
                id="period-key"
                type="number"
                min="2000"
                max="2100"
                className="input"
                value={periodKey}
                onChange={(event) => setPeriodKey(event.target.value)}
              />
            )}
          </Field>
        </div>
      </Card>

      {error && <ErrorAlert message={error} onRetry={load} />}

      {loading ? (
        <LoadingBlock label="Загрузка бюджетов…" />
      ) : (
        <div className="grid-2">
          {CURRENCIES.map((currency) => {
            const budget = byCurrency.get(currency)
            return (
              <Card
                key={currency}
                title={`Бюджет ${currency}`}
                subtitle={periodType === 'month' ? monthLabel(periodKey) : `Год ${periodKey}`}
                actions={
                  isAdmin ? (
                    <button
                      type="button"
                      className="btn btn--secondary btn--sm"
                      onClick={() => {
                        setEditTarget(currency)
                        setLimitValue(budget?.limit_amount ?? '')
                      }}
                      data-testid={`edit-budget-${currency}`}
                    >
                      {budget ? 'Изменить лимит' : 'Задать лимит'}
                    </button>
                  ) : undefined
                }
              >
                {!budget ? (
                  <EmptyState
                    icon="🎯"
                    title="Лимит не задан"
                    text={
                      isAdmin
                        ? 'Задайте лимит бюджета для этой валюты, чтобы контролировать расходы.'
                        : 'Администратор ещё не задал бюджет для этой валюты.'
                    }
                  />
                ) : (
                  <div className="stack">
                    <div className="row row--between">
                      <span className="text-muted">Лимит</span>
                      <strong className="mono-num">
                        {formatAmount(budget.limit_amount, currency)}
                      </strong>
                    </div>
                    <div className="row row--between">
                      <span className="text-muted">Запланировано</span>
                      <span className="mono-num">
                        {formatAmount(budget.planned_amount, currency)}
                      </span>
                    </div>
                    <div className="row row--between">
                      <span className="text-muted">Фактически оплачено</span>
                      <span className="mono-num">
                        {formatAmount(budget.actual_amount, currency)}
                      </span>
                    </div>
                    <div className="row row--between">
                      <span className="text-muted">Остаток</span>
                      <span
                        className="mono-num"
                        style={{ color: budget.over_limit ? 'var(--color-error)' : undefined }}
                      >
                        {formatAmount(budget.remaining, currency)}
                      </span>
                    </div>

                    <div>
                      <div className="row row--between text-small">
                        <span className="text-muted">Использование</span>
                        <span>{budget.usage_percent.toFixed(1)}%</span>
                      </div>
                      <ProgressBar
                        percent={budget.usage_percent}
                        variant={
                          budget.over_limit
                            ? 'error'
                            : budget.usage_percent >= 80
                              ? 'warning'
                              : undefined
                        }
                      />
                    </div>

                    {budget.over_limit && (
                      <div className="alert alert--error" role="status">
                        Превышение лимита на{' '}
                        {formatAmount(
                          Math.abs(Number(budget.remaining)).toFixed(2),
                          currency,
                        )}
                      </div>
                    )}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      <Modal
        open={editTarget !== null}
        title={`Лимит бюджета ${editTarget ?? ''}`}
        description={periodType === 'month' ? monthLabel(periodKey) : `Год ${periodKey}`}
        onClose={() => setEditTarget(null)}
        footer={
          <>
            <button type="button" className="btn btn--secondary" onClick={() => setEditTarget(null)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={handleSave}
              disabled={saving}
              data-testid="save-budget"
            >
              {saving ? 'Сохранение…' : 'Сохранить'}
            </button>
          </>
        }
      >
        <Field label="Лимит" htmlFor="limit-amount" hint="Сумма больше нуля">
          <input
            id="limit-amount"
            type="number"
            step="0.01"
            min="0.01"
            className="input"
            value={limitValue}
            onChange={(event) => setLimitValue(event.target.value)}
            data-testid="budget-limit-input"
          />
        </Field>
      </Modal>
    </>
  )
}
