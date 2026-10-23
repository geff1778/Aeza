/** Modal for recording or correcting the actual payment date. */

import { useEffect, useState } from 'react'
import { Field, Modal } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useToast } from '../lib/toast'
import { formatAmount, formatDate, todayIso } from '../lib/format'
import type { Occurrence } from '../lib/types'

export function PayModal({
  occurrence,
  onClose,
  onSaved,
}: {
  occurrence: Occurrence | null
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [paidAt, setPaidAt] = useState(todayIso())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (occurrence) {
      setPaidAt(occurrence.paid_at ?? todayIso())
      setError(null)
    }
  }, [occurrence])

  if (!occurrence) return null

  const isLate = paidAt > occurrence.due_date

  const handleSubmit = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.patch(`/payment-occurrences/${occurrence.id}`, {
        is_paid: true,
        paid_at: paidAt,
      })
      toast.push(isLate ? 'Сохранено: оплачено с просрочкой' : 'Сохранено: оплачено вовремя')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      title="Дата оплаты"
      description={`${occurrence.payment_title} · срок ${formatDate(occurrence.due_date)} · ${formatAmount(occurrence.amount, occurrence.currency)}`}
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
            data-testid="save-paid-date"
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
        </>
      }
    >
      <div className="stack">
        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        <Field
          label="Фактическая дата оплаты"
          htmlFor="paid-at"
          hint="Срок оплаты не изменяется — меняется только фактическая дата."
        >
          <input
            id="paid-at"
            type="date"
            className="input"
            value={paidAt}
            onChange={(event) => setPaidAt(event.target.value)}
            data-testid="paid-at-input"
          />
        </Field>

        <div className={isLate ? 'alert alert--warning' : 'alert alert--success'} role="status">
          {isLate
            ? `Дата позже срока (${formatDate(occurrence.due_date)}) — период будет отмечен как оплаченный с просрочкой.`
            : `Дата не позже срока (${formatDate(occurrence.due_date)}) — период будет отмечен как оплаченный вовремя.`}
        </div>
      </div>
    </Modal>
  )
}
