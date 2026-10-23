/** Create/edit form for a recurring payment (admin only). */

import { useEffect, useState } from 'react'
import { Field, Modal } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useToast } from '../lib/toast'
import { CURRENCIES, todayIso } from '../lib/format'
import type { Currency, Recurrence, RecurringPayment } from '../lib/types'

interface FormState {
  title: string
  description: string
  amount: string
  currency: Currency
  first_due_date: string
  recurrence: Recurrence
  anchor_day: string
}

const EMPTY: FormState = {
  title: '',
  description: '',
  amount: '',
  currency: 'RUB',
  first_due_date: todayIso(),
  recurrence: 'monthly',
  anchor_day: '',
}

export function PaymentFormModal({
  open,
  payment,
  onClose,
  onSaved,
}: {
  open: boolean
  payment?: RecurringPayment | null
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    if (payment) {
      setForm({
        title: payment.title,
        description: payment.description ?? '',
        amount: payment.amount,
        currency: payment.currency,
        first_due_date: payment.first_due_date,
        recurrence: payment.recurrence,
        anchor_day: String(payment.anchor_day),
      })
    } else {
      setForm(EMPTY)
    }
    setErrors({})
    setApiError(null)
  }, [open, payment])

  if (!open) return null

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const validate = (): boolean => {
    const next: Record<string, string> = {}
    if (!form.title.trim()) next.title = 'Укажите название'
    const amount = Number(form.amount)
    if (!form.amount || Number.isNaN(amount) || amount <= 0) {
      next.amount = 'Сумма должна быть больше нуля'
    }
    if (!CURRENCIES.includes(form.currency)) next.currency = 'Недопустимая валюта'
    if (!form.first_due_date) next.first_due_date = 'Укажите первый срок оплаты'

    if (form.anchor_day) {
      const day = Number(form.anchor_day)
      if (Number.isNaN(day) || day < 1 || day > 31) {
        next.anchor_day = 'День месяца от 1 до 31'
      }
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    setSaving(true)
    setApiError(null)

    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      amount: form.amount,
      currency: form.currency,
      first_due_date: form.first_due_date,
      recurrence: form.recurrence,
      anchor_day: form.anchor_day
        ? Number(form.anchor_day)
        : Number(form.first_due_date.slice(8, 10)),
    }

    try {
      if (payment) {
        await api.patch(`/recurring-payments/${payment.id}`, payload)
        toast.push('Регулярный платёж обновлён')
      } else {
        await api.post('/recurring-payments', payload)
        toast.push('Регулярный платёж создан, периоды сформированы')
      }
      onSaved()
    } catch (err) {
      setApiError(err instanceof ApiError ? err.detail : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      wide
      title={payment ? 'Изменить регулярный платёж' : 'Новый регулярный платёж'}
      description={
        payment
          ? 'Изменение параметров не затрагивает уже созданные периоды и их историю.'
          : 'После создания система сформирует периоды оплаты на 12 месяцев вперёд.'
      }
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleSubmit}
            disabled={saving}
            data-testid="submit-payment-form"
          >
            {saving ? 'Сохранение…' : payment ? 'Сохранить изменения' : 'Создать платёж'}
          </button>
        </>
      }
    >
      <div className="stack">
        {apiError && (
          <div className="alert alert--error" role="alert">
            {apiError}
          </div>
        )}

        <div className="form-grid">
          <Field label="Название" htmlFor="title" error={errors.title} full>
            <input
              id="title"
              className={errors.title ? 'input input--invalid' : 'input'}
              value={form.title}
              onChange={(event) => update('title', event.target.value)}
              placeholder="Например: Аренда офиса"
              data-testid="form-title"
            />
          </Field>

          <Field label="Сумма" htmlFor="amount" error={errors.amount} hint="Больше нуля">
            <input
              id="amount"
              type="number"
              step="0.01"
              min="0.01"
              className={errors.amount ? 'input input--invalid' : 'input'}
              value={form.amount}
              onChange={(event) => update('amount', event.target.value)}
              placeholder="1500.00"
              data-testid="form-amount"
            />
          </Field>

          <Field label="Валюта" htmlFor="currency" error={errors.currency}>
            <select
              id="currency"
              className="select"
              value={form.currency}
              onChange={(event) => update('currency', event.target.value as Currency)}
              data-testid="form-currency"
            >
              {CURRENCIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Первый срок оплаты"
            htmlFor="first_due_date"
            error={errors.first_due_date}
          >
            <input
              id="first_due_date"
              type="date"
              className={errors.first_due_date ? 'input input--invalid' : 'input'}
              value={form.first_due_date}
              onChange={(event) => update('first_due_date', event.target.value)}
              data-testid="form-first-due"
            />
          </Field>

          <Field label="Периодичность" htmlFor="recurrence">
            <select
              id="recurrence"
              className="select"
              value={form.recurrence}
              onChange={(event) => update('recurrence', event.target.value as Recurrence)}
            >
              <option value="monthly">Ежемесячно</option>
              <option value="quarterly">Ежеквартально</option>
              <option value="yearly">Ежегодно</option>
            </select>
          </Field>

          <Field
            label="День месяца"
            htmlFor="anchor_day"
            error={errors.anchor_day}
            hint="Если пусто — берётся день из первого срока. Для 31 числа короткие месяцы используют последний день, но дрейфа даты не происходит."
          >
            <input
              id="anchor_day"
              type="number"
              min="1"
              max="31"
              className={errors.anchor_day ? 'input input--invalid' : 'input'}
              value={form.anchor_day}
              onChange={(event) => update('anchor_day', event.target.value)}
              placeholder="10"
              data-testid="form-anchor-day"
            />
          </Field>

          <Field label="Описание" htmlFor="description" full>
            <textarea
              id="description"
              className="textarea"
              value={form.description}
              onChange={(event) => update('description', event.target.value)}
              placeholder="Необязательно"
            />
          </Field>
        </div>
      </div>
    </Modal>
  )
}
