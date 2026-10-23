/** Formatting helpers. Currency amounts are formatted per-currency and never
 * combined, so no cross-currency arithmetic happens anywhere in the UI. */

import type { Currency, PaymentStatus } from './types'

const CURRENCY_LABELS: Record<Currency, string> = {
  RUB: 'RUB',
  USD: 'USD',
  EUR: 'EUR',
}

export const CURRENCIES: Currency[] = ['RUB', 'USD', 'EUR']

export function formatAmount(amount: string | number, currency: Currency): string {
  const value = typeof amount === 'string' ? Number(amount) : amount
  if (Number.isNaN(value)) return `— ${currency}`
  const formatted = new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: value % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value)
  return `${formatted} ${CURRENCY_LABELS[currency]}`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [year, month, day] = value.split('-')
  if (!year || !month || !day) return value
  return `${day}.${month}.${year}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function todayIso(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset()
  const local = new Date(now.getTime() - offset * 60 * 1000)
  return local.toISOString().slice(0, 10)
}

export function currentMonthKey(): string {
  return todayIso().slice(0, 7)
}

export function monthLabel(key: string): string {
  const [year, month] = key.split('-').map(Number)
  if (!year || !month) return key
  return new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(
    new Date(Date.UTC(year, month - 1, 1)),
  )
}

export function shiftMonth(key: string, delta: number): string {
  const [year, month] = key.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1 + delta, 1))
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
}

export const RECURRENCE_LABELS = {
  monthly: 'Ежемесячно',
  quarterly: 'Ежеквартально',
  yearly: 'Ежегодно',
} as const

export const STATUS_LABELS: Record<PaymentStatus, string> = {
  paid_on_time: 'Оплачено вовремя',
  paid_late: 'Оплачено с просрочкой',
  overdue: 'Просрочено',
  due_soon: 'Скоро срок',
  pending: 'Ожидает оплаты',
}

export const STATUS_ORDER: PaymentStatus[] = [
  'overdue',
  'due_soon',
  'pending',
  'paid_late',
  'paid_on_time',
]

export function statusBadgeClass(status: PaymentStatus): string {
  return `badge badge--${status}`
}

export function dueHint(occurrence: {
  is_paid: boolean
  days_until_due: number
  status: PaymentStatus
}): string {
  if (occurrence.is_paid) {
    return occurrence.status === 'paid_late' ? 'Оплачено с опозданием' : 'Оплачено вовремя'
  }
  const days = occurrence.days_until_due
  if (days < 0) return `Просрочка ${Math.abs(days)} дн.`
  if (days === 0) return 'Срок сегодня'
  if (days === 1) return 'Остался 1 день'
  return `Осталось ${days} дн.`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}
