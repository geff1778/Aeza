/** Shared API types mirroring the backend schemas. */

export type Role = 'admin' | 'user'
export type Currency = 'RUB' | 'USD' | 'EUR'
export type Recurrence = 'monthly' | 'quarterly' | 'yearly'
export type BudgetPeriod = 'month' | 'year'

export type PaymentStatus =
  | 'paid_on_time'
  | 'paid_late'
  | 'overdue'
  | 'due_soon'
  | 'pending'

export interface Me {
  id: number
  username: string
  email: string | null
  role: Role
  is_active: boolean
  is_bootstrap: boolean
  created_at: string
  csrf_token: string
}

export interface UserAccount {
  id: number
  username: string
  email: string | null
  role: Role
  is_active: boolean
  is_bootstrap: boolean
  created_at: string
}

export interface RecurringPayment {
  id: number
  title: string
  description: string | null
  amount: string
  currency: Currency
  recurrence: Recurrence
  anchor_day: number
  first_due_date: string
  is_active: boolean
  created_at: string
  updated_at: string
  occurrences_count: number
  unpaid_count: number
  overdue_count: number
}

export interface Occurrence {
  id: number
  recurring_payment_id: number
  due_date: string
  amount: string
  currency: Currency
  is_paid: boolean
  paid_at: string | null
  receipt_url: string | null
  created_at: string
  updated_at: string
  status: PaymentStatus
  status_label: string
  days_until_due: number
  is_overdue: boolean
  payment_title: string
  recurrence: Recurrence
  attachment_count: number
}

export interface OccurrenceList {
  items: Occurrence[]
  total: number
}

export interface CurrencyTotals {
  currency: Currency
  upcoming: string
  overdue: string
  paid: string
}

export interface IntegrationStatus {
  telegram_configured: boolean
  telegram_hint: string | null
  smtp_configured: boolean
  smtp_hint: string | null
}

export interface Dashboard {
  today: string
  timezone: string
  totals: CurrencyTotals[]
  due_soon_count: number
  overdue_count: number
  paid_count: number
  upcoming: Occurrence[]
  recent_activity: AuditEntry[]
  integrations: IntegrationStatus
}

export interface AuditEntry {
  id: number
  actor_label: string
  action: string
  entity_type: string
  entity_id: string | null
  description: string
  changes: Record<string, unknown> | null
  created_at: string
}

export interface AuditList {
  items: AuditEntry[]
  total: number
}

export interface Budget {
  id: number
  period_type: BudgetPeriod
  period_key: string
  currency: Currency
  limit_amount: string
  planned_amount: string
  actual_amount: string
  remaining: string
  usage_percent: number
  over_limit: boolean
}

export interface CalendarDay {
  date: string
  items: Occurrence[]
}

export interface CalendarMonth {
  month: string
  days: CalendarDay[]
}

export interface Summary {
  today: string
  timezone: string
  by_currency: CurrencyTotals[]
  by_month: Array<{
    month: string
    currencies: Record<string, { planned: string; paid: string; overdue: string }>
  }>
  status_counts: Record<PaymentStatus, number>
  overdue_count: number
}

export interface Attachment {
  id: number
  occurrence_id: number
  original_name: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface NotificationLogEntry {
  id: number
  occurrence_id: number
  channel: 'telegram' | 'email'
  kind: string
  status: 'pending' | 'sent' | 'failed'
  attempts: number
  last_error: string | null
  created_at: string
  sent_at: string | null
}

export interface Health {
  status: string
  database: string
  timezone: string
  version: string
}
